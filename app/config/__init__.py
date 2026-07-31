import os
import importlib.util

parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_file = os.path.join(parent_dir, 'config.py')

spec = importlib.util.spec_from_file_location("_vyravid_settings", config_file)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

for name in dir(module):
    if not name.startswith("_"):
        globals()[name] = getattr(module, name)
