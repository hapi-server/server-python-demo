def prep_deps(package_name, import_name=None):
  """Install package if not already installed."""
  import sys
  import subprocess
  if import_name is None:
    import_name = package_name
  try:
    __import__(import_name)
    print(f"✓ {package_name} already installed")
  except ImportError:
    print(f"Installing {package_name}...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
    print(f"✓ {package_name} installed successfully")

