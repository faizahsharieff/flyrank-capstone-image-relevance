from pathlib import Path

from scripts.seed import discover_image_paths


def test_discover_image_paths_finds_supported_images_recursively(tmp_path: Path) -> None:
    fox_directory = tmp_path / "fox"
    nested_directory = fox_directory / "nested"
    nested_directory.mkdir(parents=True)
    (fox_directory / "fox.jpg").write_bytes(b"image")
    (nested_directory / "fox.webp").write_bytes(b"image")
    (fox_directory / "notes.txt").write_text("not an image", encoding="utf-8")

    image_paths = discover_image_paths(tmp_path)

    assert [path.name for path in image_paths] == ["fox.jpg", "fox.webp"]