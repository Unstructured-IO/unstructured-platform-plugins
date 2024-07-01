from pathlib import Path

from unstructured_platform_plugins.cli.schema_yaml.yaml_generator import generate_yaml

test_path = Path(__file__).parent
results_path = test_path / "expected_results"


def test_generate_yaml_simple():
    output = generate_yaml(app="test.assets.typed_dict_response:sample_function")
    file_path = results_path / "simple.yaml"
    with file_path.open("r") as f:
        expected = f.read()
    assert expected == output
