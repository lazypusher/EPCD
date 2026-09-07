def test_package_importable():
    import epcd_agent

    assert epcd_agent.__version__ == "0.1.0"
