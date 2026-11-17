"""Regression checks for Jaeger's streaming v3 OTLP search response."""
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('validate_e2e', Path(__file__).parents[1] / 'scripts/validate_e2e.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def resource(service, trace_id):
    return {'resource': {'attributes': [{'key': 'service.name', 'value': {'stringValue': service}}]},
            'scopeSpans': [{'spans': [{'traceId': trace_id}]}]}


class TraceSearchTests(unittest.TestCase):
    def test_streamed_resources_correlate_by_trace(self):
        body = '\n'.join(json.dumps({'result': {'resourceSpans': [resource(s, 'abc')]}})
                         for s in ('order-api', 'inventory-service', 'barista-service'))
        with patch.object(validator, 'request', return_value=body) as request:
            self.assertEqual(validator.trace_for(7), 'abc')
        url = request.call_args.args[0]
        self.assertIn('/api/v3/traces?', url)
        self.assertIn('query.serviceName=order-api', url)
        self.assertIn('query.startTimeMin=', url)
        self.assertIn('coffee.order_id', url)

    def test_services_in_different_traces_do_not_pass(self):
        body = json.dumps({'result': {'resourceSpans': [resource(s, str(i))
                          for i, s in enumerate(('order-api', 'inventory-service', 'barista-service'))]}})
        with self.assertRaisesRegex(RuntimeError, 'No complete distributed trace'):
            validator.distributed_trace_id(body)

    def test_service_names_match_application(self):
        import ast
        root = Path(__file__).parents[1] / 'src/coffee_shop/services'
        names = set()
        for filename in ('order.py', 'inventory.py', 'barista.py'):
            tree = ast.parse((root / filename).read_text())
            for node in tree.body:
                if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == 'SERVICE_NAME' for t in node.targets
                ):
                    names.add(ast.literal_eval(node.value))
        self.assertEqual(names, {'order-api', 'inventory-service', 'barista-service'})
        body = json.dumps({'result': {'resourceSpans': [resource(s, 'abc') for s in names]}})
        self.assertEqual(validator.distributed_trace_id(body), 'abc')

    def test_empty_response_is_diagnostic(self):
        with self.assertRaisesRegex(RuntimeError, 'observed services by trace: {}'):
            validator.distributed_trace_id('{"result":{}}')

    def test_gateway_errors_are_reported(self):
        with self.assertRaisesRegex(RuntimeError, 'Jaeger query error'):
            validator.distributed_trace_id('{"error":{"message":"storage unavailable"}}')


if __name__ == '__main__':
    unittest.main()
