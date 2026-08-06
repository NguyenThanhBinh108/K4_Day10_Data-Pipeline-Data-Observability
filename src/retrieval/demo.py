"""Agent demo - Contract G (paths).

Owner: R4 (Trinh Hai Dang).

File nay tach rieng khoi `src/retrieval/` (da hoan chinh trong starter) de R2 (Lieu)
chi can goi mot dong trong `phase1.py`, va de R4 co mot deliverable code that ma
khong cham vao `index.py`/`qa.py`/`agent.py`. `settings.paths.demo_answers` da co
san trong `core/config.py`.

Khac voi `retrieval/qa.py` (extractive, khong goi LLM), ham o day chay agent
LangChain that: agent tu quyet dinh goi tool `semantic_search_papers` hay
`lookup_paper` roi tong hop cau tra loi. Day la bang chung cho phan Agent va
multi-provider LLM cua rubric.

Buoc nay CAN API key. Neu khong khoi tao duoc agent (thieu key, sai provider...),
ham phai tra list rong va ghi ly do vao artifact - khong duoc lam vo pipeline, vi
phan con lai cua bai lab (baseline metrics, quality, freshness) khong phu thuoc LLM.
"""

from __future__ import annotations

from typing import Any

from core.config import Settings, normalized_provider
from core.utils import now_utc, write_json
from retrieval.agent import build_agent
from retrieval.index import LocalEmbeddingIndex

# Ba cau hoi mac dinh, moi cau kiem tra mot hanh vi khac nhau cua agent:
# 1) semantic - khong neu ten paper, buoc agent tu tim bang noi dung
# 2) exact lookup - neu dung title trong nhay don, kiem tool lookup_paper
# 3) ngoai pham vi corpus - kiem agent co dam noi "khong biet" thay vi bia
DEFAULT_QUESTIONS = [
    "Which indexed papers apply retrieval-augmented generation to safety or risk analysis?",
    "What retrieval strategies do the indexed agentic RAG papers use?",
    "Does the indexed corpus contain any paper about quantum error correction?",
]


def _extract_tool_names(messages: list[Any]) -> list[str]:
    """Lay ten cac tool agent da goi trong hoi thoai, lam bang chung agent dung corpus."""
    tool_names: list[str] = []
    for message in messages:
        tool_calls = getattr(message, "tool_calls", None) or []
        for call in tool_calls:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                tool_names.append(str(name))
    return tool_names


def _skip_result(settings: Settings, provider: str, reason: str) -> list[dict[str, Any]]:
    print(f"[demo] bo qua agent demo - {reason}")
    write_json(
        settings.paths.demo_answers,
        {
            "generated_at": now_utc().isoformat(),
            "provider": provider,
            "model": settings.model_name,
            "skipped": reason,
            "answers": [],
        },
    )
    return []


def run_agent_demo(
    settings: Settings,
    index: LocalEmbeddingIndex,
    questions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Chay agent tren vai cau hoi va ghi ket qua ra `settings.paths.demo_answers`.

    Tra ve list cau tra loi, hoac list rong neu khong khoi tao duoc agent (vi du
    thieu API key) - trong truong hop do artifact van duoc ghi kem ly do bo qua.
    """
    questions = questions or DEFAULT_QUESTIONS
    provider = normalized_provider(settings)

    try:
        agent = build_agent(settings=settings, index=index)
    except Exception as exc:
        # Thieu API key la truong hop binh thuong khi cham diem tren may khac, khong
        # phai loi pipeline - nen bat rong roi ghi ly do thay vi de exception lan len.
        reason = f"Khong khoi tao duoc agent voi provider '{provider}': {exc}"
        return _skip_result(settings, provider, reason)

    answers: list[dict[str, Any]] = []
    for position, question in enumerate(questions, start=1):
        print(f"[demo] ({position}/{len(questions)}) {question}")
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})
            messages = result.get("messages", [])
            final_message = messages[-1] if messages else None
            answers.append(
                {
                    "question": question,
                    "answer": getattr(final_message, "content", str(final_message)) if final_message else "",
                    "tools_used": _extract_tool_names(messages),
                    "error": None,
                }
            )
        except Exception as exc:
            print(f"[demo] cau {position} loi: {exc}")
            answers.append({"question": question, "answer": "", "tools_used": [], "error": str(exc)})

    write_json(
        settings.paths.demo_answers,
        {
            "generated_at": now_utc().isoformat(),
            "provider": provider,
            "model": settings.model_name,
            "collection": index.collection_name,
            "documents_indexed": len(index.documents),
            "answers": answers,
        },
    )
    succeeded = sum(1 for item in answers if not item["error"])
    print(f"[demo] {succeeded}/{len(answers)} cau tra loi duoc -> {settings.paths.demo_answers}")
    return answers


__all__ = ["run_agent_demo", "DEFAULT_QUESTIONS"]
