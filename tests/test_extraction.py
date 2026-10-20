import json
import unittest
from pathlib import Path
from unittest.mock import patch

from osint_digest.core.collector import extract_iocs, text_from_html
from tests.benchmark_iocs import benchmark

FIXTURES = Path(__file__).parent / 'fixtures' / 'extraction'


class ExtractionTests(unittest.TestCase):
    def test_synthetic_publisher_layouts(self):
        manifest = json.loads((FIXTURES / 'layouts.json').read_text(encoding='utf-8'))
        sources = json.loads((FIXTURES.parents[2] / 'config/sources.json').read_text())
        self.assertEqual({x['publisher'] for x in manifest}, {x['name'] for x in sources})
        with patch('socket.socket', side_effect=AssertionError('Offline fixtures only')):
            for case in manifest:
                with self.subTest(publisher=case['publisher']):
                    text, scope = text_from_html((FIXTURES / case['file']).read_text(encoding='utf-8'))
                    self.assertEqual(scope, case['scope'])
                    for value in case['include']:
                        self.assertIn(value, text)
                    for value in case['exclude']:
                        self.assertNotIn(value, text)
                    actual, capped = extract_iocs(text)
                    self.assertEqual({(x['type'], x['value']) for x in actual},
                                     {tuple(x) for x in case['expected_iocs']})
                    self.assertFalse(capped)

    def test_labeled_candidate_corpus(self):
        with patch('socket.socket', side_effect=AssertionError('Offline corpus only')):
            result = benchmark()
        for case in result['cases']:
            with self.subTest(case=case['id']):
                self.assertEqual(case['fp'], [])
                self.assertEqual(case['fn'], [])
                self.assertFalse(case['capped'])

    def test_cap_and_deduplication_are_separate_from_benchmark(self):
        text = ' '.join(f'{i:064x}' for i in range(2001))
        actual, capped = extract_iocs(text + ' ' + text)
        self.assertTrue(capped)
        self.assertEqual(len(actual), 2000)
        self.assertEqual([(x['type'], x['value']) for x in actual],
                         [(x['type'], x['value']) for x in extract_iocs(text)[0]])

    def test_valueless_class_attribute(self):
        text, scope = text_from_html('<article class><p>' + 'Research text. ' * 30 + '</p></article>')
        self.assertEqual(scope, 'article')
        self.assertIn('Research text.', text)


if __name__ == '__main__':
    unittest.main()
