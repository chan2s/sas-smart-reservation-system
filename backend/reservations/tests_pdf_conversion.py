"""Platform discovery and conversion checks for generated approval PDFs."""

import os
from pathlib import Path
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import mock

from django.test import SimpleTestCase

from reservations.services import approval_documents


class SofficeDiscoveryTests(SimpleTestCase):
    def setUp(self):
        self.clean_env = mock.patch.dict(os.environ, {"SOFFICE_PATH": ""})
        self.clean_env.start()
        self.addCleanup(self.clean_env.stop)

    def test_windows_common_installation_path_is_discovered(self):
        expected = "C:/Program Files/LibreOffice/program/soffice.exe"
        with (
            mock.patch.object(approval_documents.platform, "system", return_value="Windows"),
            mock.patch.object(approval_documents.shutil, "which", return_value=None),
            mock.patch.object(
                Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: path.as_posix() == expected,
            ),
        ):
            executable = approval_documents._find_soffice_executable()
        self.assertEqual(Path(executable).as_posix(), expected)

    def test_linux_standard_location_is_discovered(self):
        expected = "/usr/bin/soffice"
        with (
            mock.patch.object(approval_documents.platform, "system", return_value="Linux"),
            mock.patch.object(approval_documents.shutil, "which", return_value=None),
            mock.patch.object(
                Path,
                "is_file",
                autospec=True,
                side_effect=lambda path: path.as_posix() == expected,
            ),
            mock.patch.object(approval_documents.os, "access", return_value=True),
        ):
            executable = approval_documents._find_soffice_executable()
        self.assertEqual(Path(executable).as_posix(), expected)

    def test_soffice_path_environment_variable_takes_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            configured = Path(temporary) / "custom-soffice"
            configured.touch()
            with mock.patch.dict(os.environ, {"SOFFICE_PATH": str(configured)}):
                with mock.patch.object(approval_documents.shutil, "which") as which:
                    self.assertEqual(
                        approval_documents._find_soffice_executable(), str(configured)
                    )
                    which.assert_not_called()

    def test_soffice_on_path_is_discovered(self):
        with (
            mock.patch.object(
                approval_documents.shutil, "which", side_effect=lambda command: (
                    "/custom/bin/soffice" if command == "soffice" else None
                ),
            ),
            mock.patch.object(Path, "is_file", autospec=True, return_value=False),
        ):
            self.assertEqual(
                approval_documents._find_soffice_executable(), "/custom/bin/soffice"
            )

    def test_missing_executable_raises_descriptive_error_before_subprocess(self):
        with (
            mock.patch.object(approval_documents.platform, "system", return_value="Linux"),
            mock.patch.object(approval_documents.shutil, "which", return_value=None),
            mock.patch.object(Path, "is_file", autospec=True, return_value=False),
            mock.patch.object(approval_documents.os, "access", return_value=False),
            mock.patch.object(approval_documents.subprocess, "run") as run,
            tempfile.TemporaryDirectory() as temporary,
        ):
            with self.assertRaises(approval_documents.LibreOfficeUnavailableError) as caught:
                approval_documents._convert_pdf(
                    Path(temporary) / "approval.docx", Path(temporary)
                )
        self.assertIn("SOFFICE_PATH", str(caught.exception))
        run.assert_not_called()


class PdfConversionTests(SimpleTestCase):
    def test_successful_conversion_returns_existing_valid_pdf_and_captures_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docx_path = directory / "approval.docx"
            docx_path.write_bytes(b"docx input")
            pdf_bytes = b"%PDF-1.7\n" + b"valid approval document " * 10 + b"\n%%EOF"

            def convert(command, **kwargs):
                expected_pdf = directory / "approval.pdf"
                expected_pdf.write_bytes(pdf_bytes)
                self.assertEqual(command[0], "mock-soffice")
                self.assertIn("--headless", command)
                self.assertIn("--convert-to", command)
                self.assertIn("pdf", command)
                profile_argument = next(arg for arg in command if arg.startswith("-env:UserInstallation="))
                profile_url = profile_argument.split("=", 1)[1]
                self.assertTrue(profile_url.startswith("file:///"))
                if os.name == "nt":
                    self.assertRegex(profile_url, r"^file:///[A-Za-z]:/")
                self.assertTrue(kwargs["capture_output"])
                self.assertEqual(kwargs["timeout"], approval_documents.settings.LIBREOFFICE_TIMEOUT_SECONDS)
                return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")

            with mock.patch.object(
                approval_documents, "_find_soffice_executable", return_value="mock-soffice"
            ), mock.patch.object(approval_documents.subprocess, "run", side_effect=convert):
                pdf_path = approval_documents._convert_pdf(docx_path, directory)

            self.assertEqual(pdf_path, directory / "approval.pdf")
            self.assertGreater(pdf_path.stat().st_size, 0)
            self.assertTrue(pdf_path.read_bytes().startswith(b"%PDF-"))
            self.assertIn(b"%%EOF", pdf_path.read_bytes()[-1024:])

    def test_nonzero_converter_exit_is_never_reported_as_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docx_path = directory / "approval.docx"
            with (
                mock.patch.object(
                    approval_documents, "_find_soffice_executable", return_value="mock-soffice"
                ),
                mock.patch.object(
                    approval_documents.subprocess,
                    "run",
                    return_value=subprocess.CompletedProcess(
                        ["mock-soffice"], 1, stdout="", stderr="conversion failed"
                    ),
                ),
            ):
                with self.assertRaises(approval_documents.PdfConversionError) as caught:
                    approval_documents._convert_pdf(docx_path, directory)
        self.assertIn("conversion failed", str(caught.exception))

    def test_converter_success_without_valid_pdf_raises_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docx_path = directory / "approval.docx"

            def no_pdf(command, **_kwargs):
                (directory / "approval.pdf").write_bytes(b"not a pdf")
                return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

            with mock.patch.object(
                approval_documents, "_find_soffice_executable", return_value="mock-soffice"
            ), mock.patch.object(approval_documents.subprocess, "run", side_effect=no_pdf):
                with self.assertRaises(approval_documents.PdfConversionError):
                    approval_documents._convert_pdf(docx_path, directory)

    def test_timeout_is_configurable_and_reported_as_conversion_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            docx_path = directory / "approval.docx"
            profiles = []
            original_temporary_directory = tempfile.TemporaryDirectory

            def tracked_profile(*args, **kwargs):
                profile = original_temporary_directory(*args, **kwargs)
                profiles.append(Path(profile.name))
                return profile

            timeout_error = subprocess.TimeoutExpired("mock-soffice", timeout=3, stderr="still converting")
            with (
                mock.patch.object(
                    approval_documents, "_find_soffice_executable", return_value="mock-soffice"
                ),
                mock.patch.object(approval_documents.settings, "LIBREOFFICE_TIMEOUT_SECONDS", 3),
                mock.patch.object(
                    approval_documents.tempfile,
                    "TemporaryDirectory",
                    side_effect=tracked_profile,
                ),
                mock.patch.object(
                    approval_documents.subprocess, "run", side_effect=timeout_error
                ) as run,
            ):
                with self.assertRaises(approval_documents.PdfConversionError) as caught:
                    approval_documents._convert_pdf(docx_path, directory)
        self.assertIn("3 second timeout", str(caught.exception))
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertEqual(len(profiles), 1)
        self.assertFalse(profiles[0].exists())

    def test_concurrent_conversions_use_distinct_profiles_and_clean_them_up(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conversions = [root / "one", root / "two"]
            for directory in conversions:
                directory.mkdir()
            profiles = []
            profile_urls = []
            both_started = Barrier(2)
            original_temporary_directory = tempfile.TemporaryDirectory

            def tracked_profile(*args, **kwargs):
                profile = original_temporary_directory(*args, **kwargs)
                profiles.append(Path(profile.name))
                return profile

            def convert(command, **_kwargs):
                profile_arg = next(arg for arg in command if arg.startswith("-env:UserInstallation="))
                profile_urls.append(profile_arg.split("=", 1)[1])
                both_started.wait(timeout=10)
                output_dir = Path(command[command.index("--outdir") + 1])
                input_path = Path(command[-1])
                (output_dir / f"{input_path.stem}.pdf").write_bytes(
                    b"%PDF-1.7\n" + b"parallel conversion " * 10 + b"\n%%EOF"
                )
                return subprocess.CompletedProcess(command, 0, stdout="done", stderr="")

            with (
                mock.patch.object(
                    approval_documents, "_find_soffice_executable", return_value="mock-soffice"
                ),
                mock.patch.object(
                    approval_documents.tempfile,
                    "TemporaryDirectory",
                    side_effect=tracked_profile,
                ),
                mock.patch.object(approval_documents.subprocess, "run", side_effect=convert),
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                futures = [
                    pool.submit(
                        approval_documents._convert_pdf,
                        directory / "approval.docx",
                        directory,
                    )
                    for directory in conversions
                ]
                outputs = [future.result(timeout=15) for future in futures]

            self.assertEqual(len(set(profile_urls)), 2)
            self.assertEqual(len(profiles), 2)
            self.assertTrue(all(not profile.exists() for profile in profiles))
            self.assertTrue(all(output.is_file() and output.stat().st_size > 0 for output in outputs))

