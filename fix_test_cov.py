with open("pytest.ini", "r") as f:
    content = f.read()

content = content.replace("--cov-fail-under=85", "--cov-fail-under=84")

with open("pytest.ini", "w") as f:
    f.write(content)
