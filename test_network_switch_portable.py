import unittest
from types import SimpleNamespace
from unittest.mock import patch

import network_switch_portable as app


class ToggleAdapterTests(unittest.TestCase):
    def test_unknown_status_refuses_to_run_commands(self):
        with patch.object(app, "get_adapter_status", return_value="Unknown"), \
             patch.object(app.subprocess, "run") as run, \
             patch.object(app, "ps_full") as ps_full, \
             patch.object(app, "log"):
            self.assertEqual(app.toggle_adapter("Ethernet"), "Unknown")
        run.assert_not_called()
        ps_full.assert_not_called()

    def test_netsh_receives_normal_and_special_names_as_arguments(self):
        names = (
            "Ethernet 4",
            "Wi-Fi & guest; $(echo unsafe)",
            'Adapter "quoted" & guest',
        )
        for name in names:
            with self.subTest(name=name), \
                 patch.object(app, "get_adapter_status", side_effect=("Down", "Up")), \
                 patch.object(app.subprocess, "run", return_value=SimpleNamespace(
                     returncode=0, stdout="", stderr="")) as run, \
                 patch.object(app, "ps_full") as ps_full, \
                 patch.object(app.time, "sleep"), \
                 patch.object(app, "log"):
                self.assertEqual(app.toggle_adapter(name), "Up")

            args = run.call_args.args[0]
            self.assertEqual(args[4], f"name={name}")
            self.assertFalse(run.call_args.kwargs["shell"])
            ps_full.assert_not_called()

    def test_cmdlet_fallback_escapes_apostrophes_in_adapter_name(self):
        name = 'Wi-Fi\'; Start-Process calc; "quoted"; \''
        with patch.object(app, "get_adapter_status", side_effect=("Down", "Up")), \
             patch.object(app.subprocess, "run", return_value=SimpleNamespace(
                 returncode=1, stdout="", stderr="failed")), \
             patch.object(app, "ps_full", return_value=SimpleNamespace(
                 returncode=0, stdout="", stderr="")) as ps_full, \
             patch.object(app.time, "sleep"), \
             patch.object(app, "log"):
            self.assertEqual(app.toggle_adapter(name), "Up")

        self.assertEqual(
            ps_full.call_args.args[0],
            f"Enable-NetAdapter -Name '{app.ps_quote(name)}' -Confirm:$false",
        )


if __name__ == "__main__":
    unittest.main()
