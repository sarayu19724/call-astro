"""Automatic user-memory + prediction-journal service for Call-Astro.

Memory is NOT a manual CRUD feature. The LLM extracts stable, explicitly stated
user facts from normal chat, stores them, and relevant memories are retrieved
for future answers. Prediction journal entries keep the original prediction
immutable; outcomes are stored separately.
"""

import json
import re
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.memory.database import db
from app.services.llm_service import llm_service
from app.utils.logger import logger


MEMORY_EXTRACTION_PROMPT = """
You are Call-Astro's long-term memory extractor.

Read the user's latest message and extract ONLY stable, useful facts that the
user explicitly stated about themselves and that could improve future answers.
Do not infer anything. Do not store astrology predictions, temporary moods,
random one-off events, passwords, financial/account identifiers, or sensitive
personal information unless the user explicitly asks the assistant to remember it.

Examples of useful stable facts:
- I am studying engineering.
- I am applying for my first job.
- I work as a software engineer.
- I prefer answers in English.
- I am preparing for CAT.

Return ONLY valid JSON in this exact shape:
{
  "memories": [
    {
      "key": "stable_unique_key",
      "category": "education|career|goal|preference|background|other",
      "text": "Short normalized statement about the user",
      "confidence": 0.0
    }
  ]
}

If there is nothing worth remembering, return {"memories": []}.
"""


MEMORY_RETRIEVAL_PROMPT = """
You select which saved user memories are relevant to the current user question.
Use ONLY the supplied memories. Do not infer new facts.
Return ONLY valid JSON:
{"relevant_keys": ["key1", "key2"]}

Current user question:
{query}

Saved memories:
{memories}
"""


OUTCOME_DETECTION_PROMPT = """
You are a prediction-journal matcher.
Determine whether the user's latest message clearly reports what actually happened
for one of the supplied past predictions.

Do not guess. If there is no clear match, return matched=false.
Return ONLY JSON:
{
  "matched": false,
  "prediction_id": null,
  "outcome": null,
  "note": null
}

or, when clearly matched:
{
  "matched": true,
  "prediction_id": "...",
  "outcome": "brief factual outcome",
  "note": "brief context"
}

User message:
{message}

Open predictions:
{predictions}
"""


class MemoryJournalService:
    def __init__(self) -> None:
        pass

    # ------------------------------------------------------------------
    # Automatic long-term memory
    # ------------------------------------------------------------------
    def _load_memories(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = session.get("user_memory_json")
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except Exception:
            logger.warning("Could not decode user_memory_json")
            return []

    def _save_memories(self, session_id: str, session: Dict[str, Any], memories: List[Dict[str, Any]]) -> None:
        payload = json.dumps(memories, ensure_ascii=False)
        db.update_session(session_id, {"user_memory_json": payload})
        session["user_memory_json"] = payload

    def extract_and_save_memories(
        self,
        session_id: str,
        session: Dict[str, Any],
        message_text: str,
    ) -> List[Dict[str, Any]]:
        """Extract stable facts automatically and persist them.

        This is intentionally called from normal chat processing. The user does
        not need to open an edit screen or manually create a memory.
        """
        if not message_text or len(message_text.strip()) < 3:
            return []

        try:
            raw = llm_service.generate(
                prompt=MEMORY_EXTRACTION_PROMPT + f"\n\nUser message:\n{message_text}",
                json_format=True,
                temperature=0.0,
            )
            parsed = json.loads(self._strip_json_fences(raw))
            extracted = parsed.get("memories", []) if isinstance(parsed, dict) else []
            if not isinstance(extracted, list):
                return []
        except Exception as exc:
            logger.warning(f"Automatic memory extraction failed: {exc}")
            return []

        now = datetime.utcnow().isoformat()
        existing = self._load_memories(session)
        by_key = {m.get("key"): m for m in existing if m.get("key")}
        changed = False
        saved = []

        for item in extracted:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            text = str(item.get("text") or "").strip()
            category = str(item.get("category") or "other").strip()
            try:
                confidence = float(item.get("confidence", 0.0))
            except Exception:
                confidence = 0.0

            if not key or not text or confidence < 0.80:
                continue
            if len(text) > 240:
                text = text[:240].rstrip() + "."

            old = by_key.get(key)
            memory = {
                "key": key,
                "category": category,
                "text": text,
                "confidence": round(confidence, 3),
                "created_at": old.get("created_at", now) if old else now,
                "updated_at": now,
            }
            if old != memory:
                by_key[key] = memory
                changed = True
            saved.append(memory)

        if changed:
            merged = list(by_key.values())
            merged.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
            # Prevent unlimited growth from low-value facts.
            merged = merged[:100]
            self._save_memories(session_id, session, merged)
            logger.info(f"[Memory] saved/updated {len(saved)} automatic user memory item(s)")

        return saved

    def build_relevant_memory_block(
        self,
        session: Dict[str, Any],
        query: str,
        max_items: int = 6,
    ) -> str:
        """Use the LLM to select only memories useful for this response."""
        memories = self._load_memories(session)
        if not memories:
            return ""

        compact = [
            {"key": m.get("key"), "category": m.get("category"), "text": m.get("text")}
            for m in memories[:100]
        ]
        try:
            prompt = MEMORY_RETRIEVAL_PROMPT.format(
                query=query,
                memories=json.dumps(compact, ensure_ascii=False),
            )
            raw = llm_service.generate(prompt=prompt, json_format=True, temperature=0.0)
            selected = json.loads(self._strip_json_fences(raw)).get("relevant_keys", [])
            selected = [str(x) for x in selected if x]
        except Exception as exc:
            logger.warning(f"Memory retrieval failed; using keyword fallback: {exc}")
            selected = []

        if selected:
            selected_set = set(selected)
            chosen = [m for m in memories if m.get("key") in selected_set][:max_items]
        else:
            # Safe fallback when the selector fails.
            q = set(re.findall(r"[a-zA-Z0-9]+", query.lower()))
            scored = []
            for m in memories:
                words = set(re.findall(r"[a-zA-Z0-9]+", (m.get("text") or "").lower()))
                score = len(q & words)
                if score:
                    scored.append((score, m))
            scored.sort(key=lambda x: x[0], reverse=True)
            chosen = [m for _, m in scored[:max_items]]

        if not chosen:
            return ""
        return "Relevant saved user context (use naturally; do not mention the memory system):\n" + "\n".join(
            f"- {m.get('text')}" for m in chosen
        )

    # ------------------------------------------------------------------
    # Prediction journal
    # ------------------------------------------------------------------
    def _load_journal(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = session.get("prediction_journal_json")
        if not raw:
            return []
        try:
            value = json.loads(raw)
            return value if isinstance(value, list) else []
        except Exception:
            logger.warning("Could not decode prediction_journal_json")
            return []

    def _save_journal(self, session_id: str, session: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
        payload = json.dumps(entries, ensure_ascii=False)
        db.update_session(session_id, {"prediction_journal_json": payload})
        session["prediction_journal_json"] = payload

    def save_prediction(
        self,
        session_id: str,
        session: Dict[str, Any],
        *,
        question: str,
        response_text: str,
        topic: Optional[str],
        intent: Optional[str],
    ) -> Optional[str]:
        """Save the final response exactly as delivered.

        `original_prediction` is immutable. Outcome fields are separate and are
        never used to rewrite the original response.
        """
        if not response_text or not question:
            return None

        # Journal astrology readings/predictions, not profile collection replies.
        prediction_id = str(uuid.uuid4())
        entry = {
            "prediction_id": prediction_id,
            "created_at": datetime.utcnow().isoformat(),
            "question": question,
            "topic": topic,
            "intent": intent,
            "original_prediction": response_text,
            "outcome_recorded": False,
            "actual_outcome": None,
            "outcome_note": None,
            "outcome_recorded_at": None,
        }
        entries = self._load_journal(session)
        entries.append(entry)
        entries = entries[-200:]
        self._save_journal(session_id, session, entries)
        logger.info(f"[Journal] saved prediction {prediction_id}")
        return prediction_id

    def list_predictions(self, session: Dict[str, Any]) -> List[Dict[str, Any]]:
        return list(reversed(self._load_journal(session)))

    def get_prediction(self, session: Dict[str, Any], prediction_id: str) -> Optional[Dict[str, Any]]:
        for item in self._load_journal(session):
            if item.get("prediction_id") == prediction_id:
                return item
        return None

    def record_outcome(
        self,
        session_id: str,
        session: Dict[str, Any],
        prediction_id: str,
        outcome: str,
        note: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        entries = self._load_journal(session)
        for item in entries:
            if item.get("prediction_id") == prediction_id:
                item["outcome_recorded"] = True
                item["actual_outcome"] = outcome.strip()
                item["outcome_note"] = note.strip() if note else None
                item["outcome_recorded_at"] = datetime.utcnow().isoformat()
                # IMPORTANT: original_prediction is untouched.
                self._save_journal(session_id, session, entries)
                return item
        return None

    def auto_record_outcome_from_message(
        self,
        session_id: str,
        session: Dict[str, Any],
        message_text: str,
    ) -> Optional[Dict[str, Any]]:
        """If the user naturally reports an outcome, attach it to a matching
        open prediction without requiring a manual edit operation.
        """
        open_predictions = [
            p for p in self._load_journal(session)
            if not p.get("outcome_recorded")
        ]
        if not open_predictions or not message_text:
            return None

        compact = [
            {
                "prediction_id": p.get("prediction_id"),
                "question": p.get("question"),
                "topic": p.get("topic"),
                "created_at": p.get("created_at"),
            }
            for p in open_predictions[-20:]
        ]
        try:
            raw = llm_service.generate(
                prompt=OUTCOME_DETECTION_PROMPT.format(
                    message=message_text,
                    predictions=json.dumps(compact, ensure_ascii=False),
                ),
                json_format=True,
                temperature=0.0,
            )
            result = json.loads(self._strip_json_fences(raw))
        except Exception as exc:
            logger.warning(f"Automatic outcome detection failed: {exc}")
            return None

        if not result.get("matched"):
            return None
        prediction_id = result.get("prediction_id")
        outcome = str(result.get("outcome") or "").strip()
        if not prediction_id or not outcome:
            return None
        return self.record_outcome(
            session_id,
            session,
            str(prediction_id),
            outcome,
            result.get("note"),
        )

    @staticmethod
    def _strip_json_fences(value: str) -> str:
        text = (value or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        return text.strip()


memory_journal_service = MemoryJournalService()
