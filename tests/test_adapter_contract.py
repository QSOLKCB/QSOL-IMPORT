import unittest

from qsol_import.adapter_contract import (
    AdapterError,
    AdapterResult,
    conversation_record,
    message_record,
    validate_result,
)


class AdapterContractValidationTests(unittest.TestCase):
    def valid_result(self) -> AdapterResult:
        conversation = conversation_record(
            adapter_id="test/1",
            source_vendor="test",
            source_type="test.export",
            source_path="source.json",
            source_index=0,
            conversation_id="c1",
            title="title",
        )
        message = message_record(
            adapter_id="test/1",
            source_vendor="test",
            source_type="test.export",
            source_path="source.json",
            source_index=0,
            source_message_id="m1",
            conversation_id="c1",
            role="user",
            text="hello",
        )
        return AdapterResult((conversation,), (message,))

    def test_valid_result_matches_frozen_shapes(self):
        validate_result(self.valid_result(), "test/1")

    def test_extra_vendor_payload_is_rejected(self):
        result = self.valid_result()
        bad_message = dict(result.messages[0])
        bad_message["vendor_payload"] = {"raw": True}
        with self.assertRaises(AdapterError) as ctx:
            validate_result(AdapterResult(result.conversations, (bad_message,)), "test/1")
        self.assertEqual(ctx.exception.code, "invalid_message_record")

    def test_missing_required_field_is_rejected(self):
        result = self.valid_result()
        bad_conversation = dict(result.conversations[0])
        del bad_conversation["source_path"]
        with self.assertRaises(AdapterError) as ctx:
            validate_result(AdapterResult((bad_conversation,), result.messages), "test/1")
        self.assertEqual(ctx.exception.code, "invalid_conversation_record")

    def test_non_schema_types_are_rejected(self):
        result = self.valid_result()
        bad_message = dict(result.messages[0])
        bad_message["source_index"] = True
        with self.assertRaises(AdapterError):
            validate_result(AdapterResult(result.conversations, (bad_message,)), "test/1")


if __name__ == "__main__":
    unittest.main()
