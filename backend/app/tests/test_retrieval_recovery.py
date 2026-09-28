"""Offline regression tests: no real database, model download, or API calls."""
import ast
import importlib.util
import json
import logging
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from typing import Dict, Optional

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = SimpleNamespace(VECTOR_DB_DIR=self.temp.name)
        with patch.dict(sys.modules, {
            "app.config.settings": SimpleNamespace(settings=settings),
            "app.utils.logger": SimpleNamespace(logger=logging.getLogger("test")),
        }):
            self.module = load("isolated_vector_store", "rag/vector_store.py")
        self.store = self.module.vector_store
        self.store.chunks = [{"text": "career", "metadata": {"source": "book"}}]
        self.store.vectors = np.ones((1, 768), dtype=np.float32)
        self.store._rebuild_normalized_cache()
        self.store.save()
        self.provider = SimpleNamespace(
            provider="local", local_model_name="test-model",
            get_embedding=Mock(return_value=[1.0] * 384),
            get_embeddings=Mock(side_effect=lambda texts: [[1.0] * 384 for _ in texts]),
        )

    def test_mismatch_rebuilds_and_search_recovers(self):
        self.assertEqual(self.store.hybrid_search("career", [1.] * 384), [])
        self.store.ensure_compatible(self.provider)
        self.assertEqual(self.store.get_embedding_dim(), 384)
        self.assertEqual(self.store.retrieval_status, "ready")
        self.assertEqual(len(self.store.hybrid_search("career", [1.] * 384)), 1)
        self.assertEqual(np.load(self.store.vectors_path).shape, (1, 384))

    def test_matching_identity_skips_reembedding(self):
        self.store.ensure_compatible(self.provider)
        self.provider.get_embeddings.reset_mock()
        self.store.ensure_compatible(self.provider)
        self.provider.get_embeddings.assert_not_called()

    def test_same_dimension_model_change_rebuilds(self):
        self.store.ensure_compatible(self.provider)
        self.provider.get_embeddings.reset_mock()
        self.provider.local_model_name = "another-model"
        self.store.ensure_compatible(self.provider)
        self.provider.get_embeddings.assert_called_once()

    def test_failed_rebuild_preserves_original(self):
        before = Path(self.store.vectors_path).read_bytes()
        self.provider.get_embeddings.side_effect = RuntimeError("offline")
        with self.assertRaises(RuntimeError):
            self.store.ensure_compatible(self.provider)
        self.assertEqual(Path(self.store.vectors_path).read_bytes(), before)
        self.assertEqual(self.store.get_embedding_dim(), 768)
        self.assertEqual(self.store.retrieval_status, "failed")

    def test_invalid_vectors_do_not_replace_index(self):
        self.provider.get_embeddings.side_effect = lambda texts: [[0.] * 384 for _ in texts]
        with self.assertRaises(ValueError):
            self.store.ensure_compatible(self.provider)
        self.assertEqual(np.load(self.store.vectors_path).shape, (1, 768))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.validator = load("isolated_validator", "services/claim_validator.py")
        with patch.dict(sys.modules, {
            "app.services.kundli_service": SimpleNamespace(get_house_lord=Mock()),
        }):
            self.topic = load("isolated_topic", "services/topic_service.py")

    def test_high_score_cannot_authorize_job_promise(self):
        self.assertTrue(self.validator.validate_claims(
            "By late 2026 you will receive a job offer.", "2026 to 2027",
            {"confidence_pct": 99, "verdict": "favorable"}))

    def test_negative_and_positive_agreement_have_equal_strength(self):
        for positive, negative in [(2, 0), (0, 2)]:
            self.assertEqual(self.topic.get_evidence_consensus_label({
                "positive_count": positive, "negative_count": negative,
                "confidence_pct": 81 if positive else 19,
            }), "MEDIUM")

    def test_no_favorable_period_is_explicit(self):
        result = self.topic.format_dasha_timeline_for_prompt([
            {"mahadasha": "Venus", "antardasha": "Mars", "start": "2026", "end": "2027"}
        ], [])
        self.assertIn("No supported favorable timing window", result)

    def test_timing_gate_does_not_call_llm(self):
        # Load the real methods without initializing the app's database and models.
        tree = ast.parse((ROOT / "services/chat_service.py").read_text(encoding="utf-8"))
        methods = [node for cls in tree.body if isinstance(cls, ast.ClassDef)
                   for node in cls.body if isinstance(node, ast.FunctionDef)
                   and node.name in {"_generate_and_validate", "_limited_evidence_response"}]
        klass = ast.ClassDef(name="Chat", bases=[], keywords=[], body=methods, decorator_list=[])
        namespace = {"Dict": Dict, "Optional": Optional, "llm_service": Mock()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[klass], type_ignores=[])), "chat_gate", "exec"), namespace)
        for classical, timing in [(False, True), (True, False), (False, False)]:
            result = namespace["Chat"]()._generate_and_validate(
                "session", {"language": "English"}, "prompt", "2026 to 2027",
                {"requires_timing": True, "timing_supported": timing,
                 "classical_evidence_available": classical}, topic="career")
            self.assertIn("does not establish a reliable window for a job offer", result)
        namespace["llm_service"].generate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
