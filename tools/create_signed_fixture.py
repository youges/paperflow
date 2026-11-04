"""Regenerate the self-signed TEST fixture (optional: pip install pyHanko==0.38.1).

The private test key exists only in a temporary directory and is not distributed.
This sample identity is solely for regression tests, not a trusted signer.
"""
from pathlib import Path
from datetime import datetime, timezone
import tempfile
import sys

import pymupdf
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
from pyhanko.pdf_utils.reader import PdfFileReader
from pyhanko.sign import fields, signers
from pyhanko.sign.validation import validate_pdf_signature
from pyhanko_certvalidator import ValidationContext

ROOT = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "tests/fixtures/signed-test.pdf"
target.parent.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory() as temporary:
    folder = Path(temporary)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "PaperFlow TEST ONLY")])
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime(2025, 1, 1, tzinfo=timezone.utc))
            .not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=True,
                key_encipherment=False, data_encipherment=False, key_agreement=False,
                key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
            .sign(key, hashes.SHA256()))
    (folder / "key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / "cert.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    with pymupdf.open() as document:
        for index in range(3):
            page = document.new_page(width=320, height=440)
            page.insert_text((30, 50), f"SIGNED DOCUMENT PAGE {index + 1}", fontsize=15)
            if index == 0:
                widget = pymupdf.Widget()
                widget.field_name = "reference"
                widget.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
                widget.field_value = "FORM VALUE"
                widget.rect = pymupdf.Rect(30, 70, 240, 100)
                page.add_widget(widget)
            if index == 1:
                page.set_rotation(90)
                annot = page.add_text_annot((280, 60), "Keep this annotation")
                annot.update()
        document.save(str(folder / "unsigned.pdf"))
    signer = signers.SimpleSigner.load(str(folder / "key.pem"), str(folder / "cert.pem"))
    with (folder / "unsigned.pdf").open("rb") as stream, target.open("wb") as output:
        signers.PdfSigner(signers.PdfSignatureMetadata(field_name="DemoSignature"), signer=signer,
            new_field_spec=fields.SigFieldSpec(sig_field_name="DemoSignature", on_page=1,
                box=(40, 150, 280, 250))).sign_pdf(IncrementalPdfFileWriter(stream), output=output)
    with target.open("rb") as stream:
        signature = PdfFileReader(stream).embedded_signatures[0]
        status = validate_pdf_signature(signature,
            signer_validation_context=ValidationContext(trust_roots=[signer.signing_cert], allow_fetching=False))
        assert status.intact and status.valid
        print(f"Created self-signed TEST fixture; cryptographic integrity verified: {target}")
