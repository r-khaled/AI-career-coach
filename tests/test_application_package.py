import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.package_application import ROOT, build_application


class ApplicationPackageTests(unittest.TestCase):
    def test_deterministic_self_contained_package(self):
        wheels = ROOT / '.lab/application-wheels'
        if not wheels.exists():
            self.skipTest('Build the pinned wheelhouse first')
        key, body = build_application(dependency_dir=wheels)
        self.assertEqual((key, body), build_application(dependency_dir=wheels))
        self.assertEqual(key, 'lambda-artifacts/application/' + hashlib.sha256(body).hexdigest() + '.zip')
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            names = archive.namelist()
            self.assertEqual(names, sorted(names))
            self.assertIn('career_coach/handler.py', names)
            self.assertIn('career_coach/schemas/career-plan.json', names)
            self.assertIn('jsonschema/__init__.py', names)
            self.assertTrue(any(n.startswith('rpds/') and n.endswith('.so') for n in names))
            self.assertNotIn('ingestion/__init__.py', names)
            self.assertTrue(json.loads(archive.read('application-manifest.json'))['wheels'])
        worker_key, worker_body = build_application(dependency_dir=wheels, artifact_kind='worker')
        self.assertEqual(worker_key, 'lambda-artifacts/worker/' + hashlib.sha256(worker_body).hexdigest() + '.zip')
        self.assertNotEqual(body, worker_body)
        with zipfile.ZipFile(io.BytesIO(worker_body)) as archive:
            self.assertIn('career_coach/worker.py', archive.namelist())
            self.assertEqual(json.loads(archive.read('application-manifest.json'))['artifact_kind'], 'worker')

    def test_missing_dependency_or_unpinned_requirement_fails(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'career_coach').mkdir()
            (root / 'career_coach/__init__.py').write_text('')
            (root / 'requirements-application.txt').write_text('example>=1\n')
            with self.assertRaises(ValueError):
                build_application(root, root / 'wheels')
            (root / 'requirements-application.txt').write_text('example==1\n')
            (root / 'requirements-application.lock.json').write_text(json.dumps({'wheels': [
                {'name': 'example', 'version': '1', 'filename': 'example-1-py3-none-any.whl', 'sha256': '0' * 64}]}))
            with self.assertRaises(ValueError):
                build_application(root, root / 'wheels')

    def test_locked_wheel_tamper_and_extra_wheel_are_rejected_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'career_coach').mkdir()
            (root / 'career_coach/__init__.py').write_text('')
            (root / 'requirements-application.txt').write_text('example==1\n')
            wheels = root / 'wheels'
            wheels.mkdir()
            wheel = wheels / 'example-1-py3-none-any.whl'
            with zipfile.ZipFile(wheel, 'w') as archive:
                archive.writestr('example.py', 'value = 1\n')
            (root / 'requirements-application.lock.json').write_text(json.dumps({'wheels': [
                {'name': 'example', 'version': '1', 'filename': wheel.name,
                 'sha256': hashlib.sha256(wheel.read_bytes()).hexdigest()}]}))
            build_application(root, wheels)
            extra = wheels / 'example-1-py2.py3-none-any.whl'
            extra.write_bytes(wheel.read_bytes())
            with self.assertRaisesRegex(ValueError, 'unexpected wheels'):
                build_application(root, wheels)
            extra.unlink()
            wheel.write_bytes(wheel.read_bytes() + b'tamper')
            with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
                build_application(root, wheels)
