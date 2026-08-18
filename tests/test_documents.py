import io
import unittest
import zipfile

from qsol_import.documents import (
    DOCX_MEDIA_TYPE,
    DocumentExtractionError,
    extract_document_text,
)


POLICY = {
    "max_extracted_text_bytes": 1024 * 1024,
    "inner_archive_limits": {
        "max_entries": 16,
        "max_member_uncompressed_bytes": 1024 * 1024,
        "max_total_uncompressed_bytes": 2 * 1024 * 1024,
        "max_compression_ratio": 200.0,
    },
}


def docx_with_members(members: dict[str, str | bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, value in members.items():
            zf.writestr(name, value)
    return buffer.getvalue()


class DocumentContractTests(unittest.TestCase):
    def test_docx_body_text_contract_preserves_order_tabs_and_paragraphs(self):
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>A</w:t></w:r><w:tab/><w:r><w:t>B</w:t></w:r></w:p>'
            '<w:p><w:r><w:t>C</w:t></w:r></w:p></w:body></w:document>'
        )
        data = docx_with_members(
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": xml,
            }
        )
        result = extract_document_text(data, DOCX_MEDIA_TYPE, POLICY)
        self.assertEqual(result.contract, "QSOL-IMPORT/DOCX-BODY-TEXT/1")
        self.assertEqual(result.text_bytes, b"A\tB\nC\n")

    def test_docx_inner_traversal_is_rejected(self):
        data = docx_with_members(
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>',
                "../escape.txt": "nope",
            }
        )
        with self.assertRaises(DocumentExtractionError) as ctx:
            extract_document_text(data, DOCX_MEDIA_TYPE, POLICY)
        self.assertEqual(ctx.exception.code, "unsafe_inner_path")

    def test_docx_doctype_is_rejected(self):
        xml = (
            '<!DOCTYPE x [<!ENTITY boom "x">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>&boom;</w:t></w:r></w:p></w:body></w:document>'
        )
        data = docx_with_members(
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": xml,
            }
        )
        with self.assertRaises(DocumentExtractionError) as ctx:
            extract_document_text(data, DOCX_MEDIA_TYPE, POLICY)
        self.assertEqual(ctx.exception.code, "xml_doctype_rejected")

    def test_utf16_docx_doctype_is_rejected_encoding_aware(self):
        xml = (
            '<?xml version="1.0" encoding="UTF-16"?>'
            '<!DOCTYPE w:document [<!ENTITY boom "expanded">]>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            '<w:body><w:p><w:r><w:t>&boom;</w:t></w:r></w:p></w:body></w:document>'
        ).encode("utf-16")
        data = docx_with_members(
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": xml,
            }
        )
        with self.assertRaises(DocumentExtractionError) as ctx:
            extract_document_text(data, DOCX_MEDIA_TYPE, POLICY)
        self.assertEqual(ctx.exception.code, "xml_doctype_rejected")

    def test_docx_fragment_amplification_hits_extracted_text_limit(self):
        fragments = "".join("<w:r><w:t>abcd</w:t></w:r>" for _ in range(64))
        xml = (
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f"<w:body><w:p>{fragments}</w:p></w:body></w:document>"
        )
        data = docx_with_members(
            {
                "[Content_Types].xml": "<Types/>",
                "word/document.xml": xml,
            }
        )
        limited_policy = {
            **POLICY,
            "max_extracted_text_bytes": 64,
        }
        with self.assertRaises(DocumentExtractionError) as ctx:
            extract_document_text(data, DOCX_MEDIA_TYPE, limited_policy)
        self.assertEqual(ctx.exception.code, "extracted_text_limit")


if __name__ == "__main__":
    unittest.main()
