"""
Módulo 5: Geração, Guardrails e Recusas (src/generate.py)
Grande Desafio RAG - Cenário 2: Saúde Pública e Protocolos Clínicos
Em conformidade com as diretrizes do Ministério da Saúde, PCDT, RENAME e LGPD.
"""

import re
import logging
from typing import Dict, Any, List, Optional, Union
from openai import OpenAI
import json

# 1. IMPLEMENTAÇÃO DE OBSERVABILIDADE (LOGGING)
# Configuração do log para rastrear atividades e bloqueios no console ou em arquivo
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("RAG_HealthGuardrails")

# Configurações oficiais da infraestrutura compartilhada (Seção 2.1)
OLLAMA_URL = "http://ecoa-llm.duckdns.org:11434/v1"
GENERATION_MODEL = "qcwind/qwen3-8b-instruct-Q4-K-M"

ChunkInput = Union[str, Dict[str, Any]]


class HealthGuardrails:
    """Aplica guardrails de segurança clínica e conformidade com a LGPD."""

    @staticmethod
    def mask_lgpd(text: str) -> str:
        """Anonimiza identificadores e dados de contato (CPF, CNS, telefones, e-mails)."""
        if not text:
            return ""

        original_text = text
        text = re.sub(r'\b[12789]\d{14}\b', '[CNS_OCULTADO]', text)
        text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b', '[EMAIL_OCULTADO]', text)
        text = re.sub(r'\(?\+?55\)?\s?\(?\d{2}\)?\s?\d{4,5}-\d{4}\b', '[TELEFONE_OCULTADO]', text)
        text = re.sub(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b', '[CPF_OCULTADO]', text)
        text = re.sub(r'\b\d{11}\b', '[DOCUMENTO_PESSOAL_OCULTADO]', text)

        # Loga apenas se houve alguma alteração (sanitização aplicada)
        if text != original_text:
            logger.info("Guardrail LGPD ativado: Dados sensíveis anonimizados no texto.")

        return text

    @staticmethod
    def check_prescription_request(query: str) -> bool:
        """
        Detecta pedidos de conduta clínica individualizada, dosagem pessoal ou prescrição.
        Cobre primeira pessoa e terceiros/familiares (caso Sandra).
        """
        query_lower = query.lower()

        direct_triggers = [
            "devo tomar", "posso tomar", "me receita", "qual remédio para mim",
            "o que tomar", "receita para o meu", "qual comprimido tomo",
            "quanto de dosagem para mim", "posso dar para o meu filho",
            "estou com dor, o que tomo", "qual o tratamento para mim",
        ]

        if any(t in query_lower for t in direct_triggers):
            logger.warning("Guardrail Clínico Acionado (Trigger Direto).")
            return True

        family_terms = r'(meu pai|minha mãe|meu filho|minha filha|meu marido|minha esposa|meu avô|minha avó|\bele\b|\bela\b)'
        action_terms = r'(deve tomar|pode tomar|deve usar|pode usar|que rem[eé]dio|qual rem[eé]dio|qual medicamento|que dose|qual dose|posso dar)'

        if re.search(family_terms, query_lower) and re.search(action_terms, query_lower):
            logger.warning("Guardrail Clínico Acionado (Trigger Terceiros).")
            return True

        return False


class GenerationModule:
    """Orquestra a sanitização, verificação de guardrails e geração estrita com grounding."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = GENERATION_MODEL):
        self.guardrails = HealthGuardrails()
        self.model = model
        # Tratamento de erro silencioso caso o servidor LLM esteja fora do ar
        try:
            self.client = OpenAI(base_url=base_url, api_key="ollama")
        except Exception as e:
            logger.error(f"Falha na inicialização do cliente LLM: {str(e)}")
            self.client = None

    @staticmethod
    def _normalize_chunk(chunk: ChunkInput, idx: int) -> Dict[str, Any]:
        """Normaliza chunk recebido como string ou dict para dicionário padronizado."""
        if isinstance(chunk, dict):
            texto = chunk.get("texto") or chunk.get("text") or ""
            return {
                "text": texto,
                "texto": texto,
                "chunk_id": chunk.get("chunk_id", f"chunk_{idx}"),
                "vigencia": chunk.get("vigencia"),
                "secao": chunk.get("secao") or chunk.get("section") or "Seção não informada",
                "source": chunk.get("source") or chunk.get("source_file") or "Documento não informado",
                "rank": chunk.get("rank") or (idx + 1),
            }
        return {
            "text": chunk,
            "texto": chunk,
            "chunk_id": f"chunk_{idx}",
            "vigencia": None,
            "secao": "Seção não informada",
            "source": "Documento não informado",
            "rank": idx + 1,
        }

    def build_prompt(self, query: str, context_chunks: List[Dict[str, Any]]) -> str:
        """Monta o prompt com instruções de sistema estritas contra alucinações."""
        if not context_chunks:
            # 2. REFINAMENTO DE FALLBACK QUANDO NÃO HÁ EVIDÊNCIAS
            logger.info("Construção de prompt: Nenhum chunk de contexto fornecido.")
            context_text = "Nenhuma evidência documental encontrada na base do PCDT/RENAME para esta requisição."
            vigencia_note = ""
        else:
            partes = []
            vigencias = set()

            for idx, c in enumerate(context_chunks, start=1):
                rank = c.get("rank", idx)
                secao = c.get("secao") or c.get("section") or "Seção não informada"
                source = c.get("source") or c.get("source_file") or c.get("chunk_id") or "Documento não informado"
                vigencia = c.get("vigencia")

                vigencia_str = vigencia if vigencia else "Não informada"
                if vigencia:
                    vigencias.add(str(vigencia))

                cabecalho = f"[Evidência #{rank} | Seção: {secao} | Documento: {source} | Vigência: {vigencia_str}]"
                texto = c.get("texto") or c.get("text") or ""
                partes.append(f"{cabecalho}\n{texto}")

            context_text = "\n\n---\n\n".join(partes)

            vigencia_note = ""
            if len(vigencias) > 1:
                vigencia_note = (
                    "\n5. As evidências acima incluem versões de vigências diferentes do mesmo "
                    "protocolo. Não misture os conteúdos: identifique o que mudou entre as "
                    "versões e cite a data de vigência de cada trecho usado."
                )

        prompt = f"""
[SISTEMA]
Você é um assistente técnico especializado nos Protocolos Clínicos e Diretrizes Terapêuticas (PCDT) do SUS e na RENAME.
Diretrizes mandatórias de resposta:
1. Responda ESTRITAMENTE com base nas evidências dos protocolos fornecidas abaixo.
2. Nunca extrapole condutas ou invente dados fora do contexto citado.
3. Se o protocolo não abordar a questão, informe expressamente que a evidência documental é omissa sobre o ponto.
4. Nunca prescreva ou recomende conduta para um paciente individual - descreva apenas o que o protocolo estabelece em termos gerais.

[REGRAS DE INTERPRETAÇÃO DAS EVIDÊNCIAS]
5. Identifique e preserve todas as condições essenciais relevantes para a pergunta.
6. Diferencie requisitos gerais, específicos, obrigatórios, cumulativos e alternativos.
7. Não transforme condições específicas de uma situação em regras gerais.
8. Quando uma frase introduzir uma lista que continua em outro chunk, interprete os trechos em conjunto.
9. Preserve valores, limites, datas, idades, prazos, códigos e quantidades exatamente como aparecem nas evidências.
10. Não apresente informações administrativas como critérios clínicos, salvo quando o documento estabelecer expressamente essa relação.
11. Não invente requisitos, exceções ou conclusões para preencher lacunas documentais.
12. Associe as afirmações relevantes aos identificadores dos chunks que efetivamente as sustentam.
13. Não confunda datas históricas mencionadas no texto com a vigência do documento.
14. Antes de responder, confira se nenhuma condição essencial foi omitida ou generalizada indevidamente.

[ESTRUTURA ADAPTATIVA DA RESPOSTA]
- Comece com uma resposta direta à pergunta.
- Organize critérios ou informações em grupos quando necessário.
- Apresente condições específicas, exceções e restrições somente quando pertinentes.
- Indique os identificadores dos chunks que sustentam as afirmações relevantes.
- Informe limitações ou ausência de evidências somente quando necessário.
- Não crie seções vazias nem acrescente informações apenas para preencher esta estrutura.
- Evite repetições e priorize clareza, precisão e concisão.

{vigencia_note}

[EVIDÊNCIAS DOS PROTOCOLOS]
{context_text}

[PERGUNTA DO USUÁRIO]
{query}
""".strip()
        return prompt

    def build_validation_prompt(
            self,
            query: str,
            context_chunks: List[Dict[str, Any]],
            response: str,
    ) -> str:
        """Constrói contrato generalista de validação documental."""

        evidencias = [
            {
                "rank": rank,
                "chunk_id": c["chunk_id"],
                "secao": c.get("secao"),
                "source": c.get("source"),
                "vigencia": c.get("vigencia"),
                "texto": c["text"],
            }
            for rank, c in enumerate(context_chunks, start=1)
            #for c in context_chunks
        ]

        dados = {
            "pergunta": query,
            "evidencias": evidencias,
            "resposta_gerada": response,
        }

        return (
                "Você é um auditor de fidelidade documental de respostas "
                "sobre protocolos clínicos.\n\n"

                "Compare a resposta com a pergunta e as evidências fornecidas.\n"
                "As evidências são a única fonte autorizada.\n\n"

                "CONTRATO OBRIGATÓRIO DE VERIFICAÇÃO:\n"
                "1. Verifique se a resposta atende à pergunta.\n"
                "2. Identifique requisitos essenciais presentes nas evidências "
                "que foram omitidos.\n"
                "3. Verifique se condições obrigatórias e cumulativas foram preservadas.\n"
                "4. Verifique se alternativas independentes foram mantidas separadas.\n"
                "5. Detecte alterações de operadores lógicos, especialmente E e OU.\n"
                "6. Verifique idades, valores, códigos, quantidades, datas e limites.\n"
                "7. Detecte afirmações não sustentadas pelas evidências.\n"
                "8. Verifique se condições específicas foram generalizadas indevidamente.\n"
                "9. Verifique se as fontes citadas sustentam as afirmações.\n"
                "10. Se faltar evidência necessária, registre a limitação; "
                "não invente informação.\n\n"

                "CONFERÊNCIA LÓGICA OBRIGATÓRIA:\n"
                "- Identifique individualmente cada condição relevante "
                "presente nas evidências.\n"
                "- Compare cada condição com a afirmação correspondente "
                "na resposta.\n"
                "- Verifique se alternativas independentes foram "
                "indevidamente fundidas em uma única condição.\n"
                "- Compare explicitamente operadores cumulativos (E) "
                "e alternativos (OU), preservando seu significado.\n"
                "- Verifique se uma condição foi ampliada ou restringida "
                "pela substituição de conectivos.\n"
                "- Registre cada divergência encontrada no campo "
                "apropriado do JSON.\n"
                "- Não considere a resposta fiel apenas porque "
                "o assunto principal foi identificado corretamente.\n\n"

                "Avalie apenas os requisitos aplicáveis à pergunta.\n"
                "Não exija campos clínicos irrelevantes.\n"
                "Não trate informações administrativas como critérios clínicos "
                "sem suporte explícito.\n"
                "Não considere ausência de informação nos chunks como prova "
                "de ausência no protocolo completo.\n\n"

                "Responda exclusivamente com um objeto JSON válido, "
                "sem Markdown, contendo:\n"
                "{\n"
                '  "responde_pergunta": true,\n'
                '  "condicoes_omitidas": [],\n'
                '  "alteracoes_logicas": [],\n'
                '  "afirmacoes_sem_suporte": [],\n'
                '  "generalizacoes_indevidas": [],\n'
                '  "problemas_de_citacao": [],\n'
                '  "evidencias_insuficientes": [],\n'
                '  "justificativa": "",\n'
                '  "afirmacoes": []\n'
                "}\n\n"

                "Use listas vazias quando não encontrar problemas. "
                "Cada problema identificado deve explicar a divergência "
                "e indicar os chunks relevantes.\n\n"

                "ANÁLISE POR AFIRMAÇÃO: No campo afirmacoes, retorne uma lista de "
                "objetos com texto, status, chunk_ids e justificativa. "
                "O texto deve ser um trecho literal e contínuo da resposta_gerada. "
                "O status deve ser sustentada, sem_suporte, contraditoria ou nao_verificada. "
                "Use contraditoria apenas quando existir conflito explícito. "
                "Em chunk_ids, use somente identificadores das evidências fornecidas. "
                "Não invente trechos ou referências.\n\n"
                "DADOS PARA AVALIAÇÃO:\n"
                + json.dumps(dados, ensure_ascii=False, indent=2)
        )

    def validate_response(
            self,
            query: str,
            context_chunks: List[Dict[str, Any]],
            response: str,
    ) -> Dict[str, Any]:
        """Avalia a fidelidade da resposta às evidências fornecidas."""

        campos_lista = (
            "condicoes_omitidas",
            "alteracoes_logicas",
            "afirmacoes_sem_suporte",
            "generalizacoes_indevidas",
            "problemas_de_citacao",
            "evidencias_insuficientes",
        )

        def pendente(
                motivo: str,
                relatorio: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            return {
                "status": "review_required",
                "validated": False,
                "reason": motivo,
                "report": relatorio,
            }

        if not self.client:
            return pendente("Cliente LLM indisponível para validação.")

        if not context_chunks or not response.strip():
            return pendente("Evidências ou resposta ausentes.")

        chunks = [
            self._normalize_chunk(c, i)
            for i, c in enumerate(context_chunks)
        ]

        pergunta_segura = self.guardrails.mask_lgpd(query)
        resposta_segura = self.guardrails.mask_lgpd(response)

        chunks_seguros = [
            {
                **c,
                "text": self.guardrails.mask_lgpd(c["text"]),
            }
            for c in chunks
        ]

        prompt = self.build_validation_prompt(
            query=pergunta_segura,
            context_chunks=chunks_seguros,
            response=resposta_segura,
        )

        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=1500,
                extra_body={"think": False},
            )

            texto = completion.choices[0].message.content or ""
            texto = texto.strip()

            # Aceita JSON puro ou envolvido em bloco Markdown.
            if texto.startswith("```"):
                linhas = texto.splitlines()
                if len(linhas) >= 3 and linhas[-1].strip() == "```":
                    texto = "\n".join(linhas[1:-1]).strip()

            try:
                relatorio = json.loads(texto)

            except json.JSONDecodeError as exc:
                logger.warning(
                    "JSON inválido na validação documental | "
                    "linha=%d | coluna=%d | posição=%d | "
                    "tamanho_resposta=%d | resposta_vazia=%s",
                    exc.lineno,
                    exc.colno,
                    exc.pos,
                    len(texto),
                    not bool(texto),
                )

                return pendente(
                    "O validador retornou uma resposta em formato inválido."
                )

            if not isinstance(relatorio, dict):
                return pendente("Validador não retornou objeto JSON.")

            if type(relatorio.get("responde_pergunta")) is not bool:
                return pendente("Campo responde_pergunta inválido.")

            for campo in campos_lista:
                valor = relatorio.get(campo)

                if not isinstance(valor, list):
                    return pendente(f"Campo inválido: {campo}")

                if not all(
                        isinstance(item, str) and item.strip()
                        for item in valor
                ):
                    return pendente(
                        f"Itens inválidos no campo: {campo}",
                        relatorio,
                    )

            if not isinstance(relatorio.get("justificativa"), str):
                return pendente("Campo justificativa inválido.")

            # As marcações são sugestões do auditor LLM, não prova de correção.
            # Só aceitamos trechos literais e IDs realmente recuperados.
            afirmacoes_validas = []
            ids_validos = {c["chunk_id"] for c in chunks}
            itens = relatorio.get("afirmacoes", [])
            if not isinstance(itens, list):
                itens = []
            for item in itens:
                if not isinstance(item, dict):
                    continue
                trecho = item.get("texto")
                status = item.get("status")
                refs = item.get("chunk_ids")
                justificativa = item.get("justificativa")
                if (isinstance(trecho, str) and trecho.strip() and trecho in response
                        and status in {"sustentada", "sem_suporte", "contraditoria", "nao_verificada"}
                        and isinstance(refs, list)
                        and all(isinstance(ref, str) and ref in ids_validos for ref in refs)
                        and isinstance(justificativa, str)):
                    afirmacoes_validas.append({"texto": trecho, "status": status,
                                               "chunk_ids": refs, "justificativa": justificativa})
            relatorio["afirmacoes"] = afirmacoes_validas

            problemas = {
                campo: relatorio[campo]
                for campo in campos_lista
                if relatorio[campo]
            }

            aprovado = (
                    relatorio["responde_pergunta"]
                    and not problemas
                    and not any(a["status"] != "sustentada" for a in afirmacoes_validas)
            )

            return {
                "status": "validated" if aprovado else "review_required",
                "validated": aprovado,
                "reason": (
                    "Nenhuma divergência identificada pelo validador."
                    if aprovado
                    else "A avaliação identificou pendências documentais."
                ),
                "report": relatorio,
            }

        except Exception as exc:
            logger.error(
                "Falha na validação documental: %s",
                type(exc).__name__,
            )
            return pendente(
                "Não foi possível concluir a validação documental."
            )

    def generate_response(
            self,
            query: str,
            context_chunks: Optional[List[ChunkInput]] = None,
            call_llm: bool = False,
            validate: bool = False,
            nivel_resposta: str = "Mínima",
    ) -> Dict[str, Any]:
        """Processa o fluxo completo do Módulo 5."""
        logger.info(f"Iniciando processamento da query. Call_LLM: {call_llm}")

        if nivel_resposta not in {"Mínima", "Intermediária", "Completa"}:
            raise ValueError("Nível de resposta inválido")

        raw_chunks = context_chunks or []
        chunks = [self._normalize_chunk(c, i) for i, c in enumerate(raw_chunks)]

        sanitized_query = self.guardrails.mask_lgpd(query)

        if self.guardrails.check_prescription_request(sanitized_query):
            refusal_text = (
                "⚠️ **Aviso de Diretriz e Segurança Clínica:**\n"
                "Como assistente de apoio técnico aos protocolos do SUS, este sistema é estritamente "
                "informativo e não está autorizado a fornecer prescrições, validar dosagens "
                "ou indicar tratamentos individualizados, seja para o usuário ou terceiros.\n\n"
                "Para diagnóstico, prescrição e acompanhamento terapêutico adequado, "
                "por favor, procure um profissional médico ou dirija-se à Unidade Básica de Saúde (UBS)."
            )
            return {
                "status": "refused_prescription",
                "stage": "validacao",
                "is_refusal": True,
                "sanitized_query": sanitized_query,
                "response": refusal_text,
                "sources_used": [],
                "prompt": None,
                "tokens": {"prompt": 0, "completion": 0, "total": 0},
            }

        sanitized_chunks = [{**c, "text": self.guardrails.mask_lgpd(c["text"])} for c in chunks]

        # 3. FALLBACK DE BUSCA VAZIA (Sem contexto)
        if not sanitized_chunks:
            logger.warning("Geração abortada: A busca retornou vazia. Acionando Fallback.")
            return {
                "status": "no_context_found",
                "stage": "geracao",
                "is_refusal": False,
                "sanitized_query": sanitized_query,
                "response": (
                    "ℹ️ **Informação Indisponível:**\n"
                    "Não encontrei evidências nos Protocolos Clínicos (PCDT) ou na base RENAME "
                    "para responder a esta pergunta específica. Por favor, tente reformular a busca "
                    "utilizando termos técnicos ou o nome do princípio ativo."
                ),
                "sources_used": [],
                "prompt": None,
                "tokens": {"prompt": 0, "completion": 0, "total": 0},
            }

        niveis = {
            "Mínima": (1000,
                       "Responda de modo objetivo e conciso. Preserve todos os critérios e condições essenciais; se não couberem, indique a insuficiência de espaço sem omiti-los silenciosamente."),
            "Intermediária": (1800,
                              "Explique os critérios e condições relevantes, incluindo exceções necessárias, de modo organizado e sem repetições."),
            "Completa": (2000,
                         "Apresente explicação aprofundada dos critérios, restrições e exceções relevantes, sem acrescentar informações não sustentadas."),
        }
        limite_tokens, instrucao_nivel = niveis[nivel_resposta]
        prompt = self.build_prompt(sanitized_query, sanitized_chunks)
        prompt += ("\n\n[NÍVEL DE DETALHAMENTO]\n" + instrucao_nivel
                   + "\nA concisão nunca autoriza omitir condições clínicas indispensáveis. "
                     "Cite os IDs dos chunks utilizados.")
        finish_reason = None
        response_text = "Síntese baseada estritamente nas evidências dos protocolos recuperados."
        tokens = {"prompt": 0, "completion": 0, "total": 0}

        if call_llm:
            if not self.client:
                # Fallback caso o cliente não tenha sido inicializado
                logger.error("Tentativa de chamada LLM falhou: Cliente OpenAI não inicializado.")
                response_text = "⚠️ Erro interno do sistema: O serviço de IA encontra-se indisponível no momento."
            else:
                try:
                    logger.info(f"Enviando prompt ao LLM ({self.model})...")
                    completion = self.client.chat.completions.create(
                        model=self.model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.1,
                        max_tokens=limite_tokens,
                        extra_body={"think": False},
                    )

                    choice = completion.choices[0]
                    message = choice.message

                    content = message.content or ""
                    reasoning = getattr(message, "reasoning", None) or ""

                    logger.info(
                        "DIAGNOSTICO LLM | finish_reason=%s | "
                        "tokens_saida=%s | caracteres_content=%d | "
                        "caracteres_reasoning=%d",
                        choice.finish_reason,
                        completion.usage.completion_tokens if completion.usage else None,
                        len(content),
                        len(reasoning),
                    )

                    finish_reason = completion.choices[0].finish_reason
                    response_text = completion.choices[0].message.content or ""
                    if finish_reason == "length":
                        logger.warning("Geração interrompida por limite de tokens (%d).", limite_tokens)
                        response_text = ""
                    if completion.usage:
                        tokens = {
                            "prompt": completion.usage.prompt_tokens,
                            "completion": completion.usage.completion_tokens,
                            "total": completion.usage.total_tokens,
                        }
                    logger.info("Resposta gerada pelo LLM com sucesso.")
                except Exception as e:
                    logger.error(f"Erro na comunicação com o LLM: {str(e)}")
                    response_text = (
                        "⚠️ **Erro de Comunicação:**\n"
                        "Houve um problema de conexão com o servidor de inteligência artificial "
                        "do laboratório. Por favor, tente novamente em instantes."
                    )

        safe_response = self.guardrails.mask_lgpd(response_text)

        geracao_incompleta = finish_reason == "length"
        erro_geracao = (
                call_llm
                and (
                        not self.client
                        or not safe_response.strip()
                        or safe_response.startswith("⚠️")
                )
        )

        validation = None

        if validate:
            if not call_llm:
                validation = {
                    "status": "not_executed",
                    "validated": False,
                    "reason": "Geração pelo LLM não solicitada.",
                    "report": None,
                }
            elif erro_geracao:
                validation = {
                    "status": "review_required",
                    "validated": False,
                    "reason": "Geração não concluída com sucesso.",
                    "report": None,
                }
            else:
                validation = self.validate_response(
                    query=sanitized_query,
                    context_chunks=sanitized_chunks,
                    response=safe_response,
                )

        if geracao_incompleta:
            status_final = "generation_incomplete"
        elif erro_geracao:
            status_final = "generation_error"
        elif validate:
            status_final = validation["status"]
        else:
            status_final = "approved"

        return {
            "status": status_final,
            "stage": "geracao",
            "is_refusal": False,
            "sanitized_query": sanitized_query,
            "prompt": prompt,
            "response": safe_response,
            "sources_used": [c["chunk_id"] for c in sanitized_chunks],
            "tokens": tokens,
            "nivel_resposta": nivel_resposta,
            "limite_tokens": limite_tokens,
            "finish_reason": finish_reason,
            "validation": validation,
        }


if __name__ == "__main__":
    module = GenerationModule()

    print("\n--- TESTE 1: recusa clínica e mascaramento LGPD (pedido direto) ---")
    q1 = "Meu CPF é 123.456.789-01 e Cartão SUS 700000000000001. O que tomar para minha hipertensão?"
    r1 = module.generate_response(query=q1, context_chunks=["PCDT Hipertensão: Losartana 50mg..."])
    print(f"is_refusal: {r1['is_refusal']}")
    print(f"sources_used: {r1['sources_used']}")
    print(f"Query mascarada: {r1['sanitized_query']}")

    print("\n--- TESTE 2: recusa clínica em terceira pessoa (caso Sandra do enunciado) ---")
    q2 = "Meu pai tem 68 anos e pressão alta. Que remédio ele deve tomar?"
    r2 = module.generate_response(query=q2, context_chunks=[])
    print(f"is_refusal: {r2['is_refusal']}  (esperado: True)")

    print("\n--- TESTE 3: consulta técnica legítima, com duas vigências ---")
    q3 = "O que mudou no critério de início de insulinoterapia no protocolo mais recente?"
    chunks3 = [
        {"chunk_id": "pcdt_dm2_2021_s4", "vigencia": "2021",
         "text": "Critério: HbA1c > 9% após falha de duas classes orais."},
        {"chunk_id": "pcdt_dm2_2024_s4", "vigencia": "2024",
         "text": "Critério: HbA1c > 8,5% após falha de duas classes orais."},
    ]
    r3 = module.generate_response(query=q3, context_chunks=chunks3)
    print(f"is_refusal: {r3['is_refusal']}")
    print(f"sources_used: {r3['sources_used']}")

    print("\n--- TESTE 4: Teste de Fallback de contexto vazio ---")
    q4 = "Qual o protocolo para tratamento de doença rara que não está no RENAME?"
    r4 = module.generate_response(query=q4, context_chunks=[])
    print(f"Status: {r4['status']}")
    print(f"Resposta de fallback:\n{r4['response']}")
