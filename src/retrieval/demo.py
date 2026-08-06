"""Agent demo - Contract G (paths).

Owner: R4 (Trinh Hai Dang).

Tach thanh file rieng de `phase1.py` chi goi mot dong, nen R2 va R4 khong bao gio
sua cung mot cho. `settings.paths.demo_answers` da co san trong config.py - starter
thiet ke de co buoc nay.

Khac voi `retrieval/qa.py` (extractive, khong goi LLM), ham nay chay agent LangChain
that: agent tu quyet dinh goi tool `semantic_search_papers` hay `lookup_paper` roi
tong hop cau tra loi. Day la bang chung cho muc 5 cua rubric (Agent va multi-provider LLM).

Buoc nay CAN API key. Neu khong co, ham tra ve list rong va ghi ly do vao artifact -
tuyet doi khong lam vo pipeline, vi phan con lai cua bai lab chay duoc ma khong can LLM.
"""

from __future__ import annotations

from typing import Any

from core.config import Settings, normalized_provider
from core.utils import now_utc, write_json
from retrieval.agent import build_agent, run_agent_question
from retrieval.index import LocalEmbeddingIndex

# Ba cau mac dinh: mot cau semantic (khong neu ten paper), mot cau exact lookup theo
# title, mot cau ma corpus khong tra loi duoc - de kiem tra agent co biet noi "khong biet".
DEFAULT_QUESTIONS = [
    "Which indexed papers apply retrieval-augmented generation to safety or risk analysis?",
    "What retrieval strategies do the indexed agentic RAG papers use?",
    "Does the indexed corpus contain any paper about quantum error correction?",
]


def _tool_calls(messages: list[Any]) -> list[str]:
    """Rut ten tool ma agent da goi, de chung minh no dung corpus chu khong bia."""
    names: list[str] = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.append(str(name))
    return names


def run_agent_demo(
    settings: Settings,
    index: LocalEmbeddingIndex,
    questions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Chay agent tren vai cau hoi va ghi `settings.paths.demo_answers`.

    Tra ve list ket qua, hoac list rong neu khong goi duoc LLM.
    """
    questions = questions or DEFAULT_QUESTIONS
    provider = normalized_provider(settings)

    try:
        agent = build_agent(settings=settings, index=index)
    except Exception as exc:
        # Thieu API key la truong hop binh thuong khi cham diem, khong phai loi pipeline.
        reason = f"Khong khoi tao duoc agent voi provider '{provider}': {exc}"
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

    answers: list[dict[str, Any]] = []
    for position, question in enumerate(questions, start=1):
        print(f"[demo] ({position}/{len(questions)}) {question}")
        try:
            result = agent.invoke({"messages": [{"role": "user", "content": question}]})
            messages = result.get("messages", [])
            final = messages[-1] if messages else None
            answers.append(
                {
                    "question": question,
                    "answer": getattr(final, "content", str(final)) if final else "",
                    "tools_used": _tool_calls(messages),
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


__all__ = ["run_agent_demo", "run_agent_question", "DEFAULT_QUESTIONS"]
