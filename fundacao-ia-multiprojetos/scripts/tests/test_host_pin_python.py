"""Pin do Python: política pura com metadados fictícios; integração real no test_host_windows."""
from __future__ import annotations

import json
import unittest

from apoio import SKILL
from test_host_windows import _Base

MANIFESTO = SKILL / "assets" / "host" / "windows" / "pins-python.json"
SUBJECT = "CN=Python Software Foundation, O=Python Software Foundation, L=Beaverton, S=Oregon, C=US"
ISSUER = "CN=Microsoft ID Verified CS AOC CA 01, O=Microsoft Corporation, C=US"
THUMBPRINT = "DE01DAAE82D04F466A576E178F6B07A839238953"


class PinPython(_Base):
    def conferir_pin(self, *, subject=SUBJECT, issuer=ISSUER, thumbprint=THUMBPRINT, status="Valid",
                     versao="3.12.10", politica=None):
        metadados = json.dumps({"Status": status, "SignerCertificate": {"Subject": subject, "Issuer": issuer,
                              "Thumbprint": thumbprint, "NotAfter": "2025-04-10T00:00:00Z"}})
        return self.ps("$sig = '" + metadados + "' | ConvertFrom-Json\n"
                       + ("$pol = '" + json.dumps(politica) + "' | ConvertFrom-Json\n" if politica is not None else "")
                       + "Test-CertificadoPython -Assinatura $sig -Versao '" + versao + "'"
                       + (" -Politica $pol" if politica is not None else "") + " | ConvertTo-Json -Compress -Depth 5")

    def test_pin_oficial_e_valido_mesmo_com_notafter_passado(self):
        r = self.conferir_pin()
        self.assertTrue(r["Ok"], r)
        self.assertEqual(r["Motivos"], [])
        self.assertEqual(r["Thumbprint"], THUMBPRINT)

    def test_nome_igual_com_certificado_ou_emissor_diferente_recusa(self):
        for kwargs in ({"thumbprint": "A" * 40}, {"issuer": "CN=Outro emissor"},
                       {"subject": "CN=Python Software Foundation"}, {"versao": "3.13.0"}):
            with self.subTest(kwargs=kwargs):
                r = self.conferir_pin(**kwargs)
                self.assertFalse(r["Ok"], r)
                self.assertTrue(r["Motivos"])

    def test_pin_igual_com_authenticode_invalida_recusa(self):
        for status in ("UnknownError", "NotTrusted", "HashMismatch", "NotSigned"):
            with self.subTest(status=status):
                self.assertFalse(self.conferir_pin(status=status)["Ok"])

    def test_politica_sem_pin_ou_invalida_nao_tem_fallback(self):
        for politica in ({"schema_version": "1", "pins": []}, {}, {"schema_version": "2", "pins": []}):
            with self.subTest(politica=politica):
                r = self.conferir_pin(politica=politica)
                self.assertFalse(r["Ok"], r)
                self.assertTrue(r["Motivos"])


class ProvenienciaDoPin(unittest.TestCase):
    def test_manifesto_vincula_certificado_a_release_e_fonte_oficial(self):
        m = json.loads(MANIFESTO.read_text(encoding="utf-8"))
        self.assertEqual(m["schema_version"], "1")
        pin = m["pins"][0]
        self.assertEqual((pin["python_version"], pin["thumbprint"], pin["subject"], pin["issuer"]),
                         ("3.12.10", THUMBPRINT, SUBJECT, ISSUER))
        self.assertEqual(pin["verified_on"], "2026-10-22")
        self.assertEqual(pin["source_url"], "https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip")
        self.assertEqual(pin["source_sha256"], "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3")
        self.assertEqual(pin["python_exe_sha256"], "4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a")


if __name__ == "__main__":
    unittest.main()
