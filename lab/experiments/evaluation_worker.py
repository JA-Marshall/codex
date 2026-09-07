"""Unprivileged observation worker; expected answers stay in the host evaluator."""

import importlib.util
from copy import deepcopy
import json
import os
from pathlib import Path
import runpy
import socket
import sys
import unittest

repository = Path(sys.argv[1])
mode = sys.argv[2]
sys.path.insert(0, str(repository))

if mode == "probe":
    assert "MODEL_API_KEY" not in os.environ
    try:
        Path(sys.argv[3]).read_bytes()
    except OSError:
        pass
    else:
        raise RuntimeError("private host input is readable")
    try:
        (repository / "evaluator-must-not-write").write_text("denied")
    except OSError:
        pass
    else:
        raise RuntimeError("candidate repository is writable")
    try:
        socket.create_connection(("1.1.1.1", 443), timeout=0.2).close()
    except OSError:
        pass
    else:
        raise RuntimeError("evaluator networking is available")
    print("isolated")
elif mode == "api":
    request = json.load(sys.stdin)
    module_name = request["module"]
    spec = importlib.util.spec_from_file_location(
        module_name, repository / (module_name + ".py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observations = []
    for arguments in request["arguments"]:
        before = deepcopy(arguments)
        try:
            observation = {"value": getattr(module, request["function"])(*arguments)}
        except ValueError:
            observation = {"error": "ValueError"}
        except Exception as error:
            observation = {"error": type(error).__name__}
        # Use serialized equality so Python's True == 1 does not mask mutation.
        if json.dumps(before, sort_keys=True) != json.dumps(arguments, sort_keys=True):
            observation = {"error": "InputMutated"}
        observations.append(observation)
    print(json.dumps(observations, sort_keys=True))
elif mode == "cli":
    sys.argv = [str(repository / "cli.py"), sys.argv[3]]
    runpy.run_path(str(repository / "cli.py"), run_name="__main__")
elif mode == "public":
    suite = unittest.defaultTestLoader.discover(sys.argv[3])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() and result.testsRun > 0 else 1)
else:
    raise ValueError("unknown observation mode")
