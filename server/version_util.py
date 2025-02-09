from packaging.version import Version

def is_version_less_or_equal_than(target_version_str, actual_version_str):
  try:
    target_version = Version(target_version_str)
    actual_version = Version(actual_version_str)
    return target_version >= actual_version
  except Exception:
    return False
