from datetime import datetime, timezone
import sys
import types
import unittest

if "psycopg" not in sys.modules:
    psycopg = types.ModuleType("psycopg")
    psycopg.connect = None
    psycopg_rows = types.ModuleType("psycopg.rows")
    psycopg_rows.dict_row = object()
    sys.modules["psycopg"] = psycopg
    sys.modules["psycopg.rows"] = psycopg_rows

from api.dark_jutsu_api import _encode_legacy_key, _merge_automus_payload


class AutomusPayloadMergeTest(unittest.TestCase):
    def test_preserves_history_adjustments_and_movements(self) -> None:
        key = _encode_legacy_key("3111000001")
        previous = {
            "dados": [{"protheus": "3111000001", "saldo": 10}],
            "ajustesItens": {
                key: {"itemKey": "3111000001", "minimo": 2, "maximo": 8, "reposicao": 6}
            },
            "historicoSaldo": {
                key: [{"timestamp": 1, "delta": -1, "saldoAnterior": 11, "saldoAtual": 10, "tipo": "saida"}]
            },
            "movimentacoesMata185": {"itens": [1]},
        }
        incoming = {
            "dados": [
                {"protheus": "3111000001", "saldo": 7},
                {
                    "protheus": "3111000002",
                    "saldo": 1,
                    "minimo": 5,
                    "maximo": 12,
                    "reposicao": 7,
                    "limitesOrigem": "automatico",
                    "sugestaoEstoque": {"fonte": "automus_antigo"},
                },
            ],
            "ajustesItens": {},
            "historicoSaldo": {},
        }

        merged = _merge_automus_payload(incoming, previous, datetime(2026, 7, 20, tzinfo=timezone.utc))

        self.assertEqual(len(merged["historicoSaldo"][key]), 2)
        self.assertEqual(merged["historicoSaldo"][key][-1]["delta"], -3.0)
        self.assertEqual(merged["dados"][0]["minimo"], 2)
        self.assertEqual(merged["dados"][0]["limitesOrigem"], "manual")
        self.assertNotIn("minimo", merged["dados"][1])
        self.assertNotIn("sugestaoEstoque", merged["dados"][1])
        self.assertEqual(merged["movimentacoesMata185"], {"itens": [1]})


if __name__ == "__main__":
    unittest.main()
