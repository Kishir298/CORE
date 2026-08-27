from core.cli.main import create_parser, execute
from core.runtime import Runtime, RuntimeState


def test_parser_status():
    parser = create_parser()

    args = parser.parse_args(["status"])

    assert args.command == "status"


def test_parser_start():
    parser = create_parser()

    args = parser.parse_args(["start"])

    assert args.command == "start"


def test_parser_stop():
    parser = create_parser()

    args = parser.parse_args(["stop"])

    assert args.command == "stop"


def test_parser_services():
    parser = create_parser()

    args = parser.parse_args(["services"])

    assert args.command == "services"


def test_parser_resources():
    parser = create_parser()

    args = parser.parse_args(["resources"])

    assert args.command == "resources"


def test_parser_connections():
    parser = create_parser()

    args = parser.parse_args(["connections"])

    assert args.command == "connections"


def test_parser_health():
    parser = create_parser()

    args = parser.parse_args(["health"])

    assert args.command == "health"


def test_status_command(capsys):
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["status"])

    execute(args, runtime)

    output = capsys.readouterr().out

    assert "Runtime: STOPPED" in output


def test_start_command():
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["start"])

    result = execute(args, runtime)

    assert result == 0
    assert runtime.state == RuntimeState.RUNNING


def test_stop_command():
    runtime = Runtime()
    runtime.start()

    parser = create_parser()

    args = parser.parse_args(["stop"])

    result = execute(args, runtime)

    assert result == 0
    assert runtime.state == RuntimeState.STOPPED


def test_services_command(capsys):
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["services"])

    execute(args, runtime)

    assert "Services:" in capsys.readouterr().out


def test_resources_command(capsys):
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["resources"])

    execute(args, runtime)

    assert "Resources:" in capsys.readouterr().out


def test_connections_command(capsys):
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["connections"])

    execute(args, runtime)

    assert "Connections:" in capsys.readouterr().out


def test_health_command(capsys):
    runtime = Runtime()
    parser = create_parser()

    args = parser.parse_args(["health"])

    execute(args, runtime)

    assert "Health:" in capsys.readouterr().out
