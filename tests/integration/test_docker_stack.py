def test_compose_has_required_services():
    from pathlib import Path
    compose=(Path(__file__).parents[2]/"docker-compose.yml").read_text()
    for service in ["db:","redis:","rabbitmq:","gateway:","alert-routing:","incident:"]:
        assert service in compose
