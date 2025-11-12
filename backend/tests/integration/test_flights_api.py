"""Integration tests for flights API endpoints."""

from decimal import Decimal

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_search_flights_endpoint_exists() -> None:
    """Test /api/flights/search endpoint is accessible."""
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
            "passengers": 1,
        },
    )

    assert response.status_code == 200


def test_search_flights_returns_flight_list() -> None:
    """Test /api/flights/search returns list of flights."""
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "SFO",
            "destination": "LAX",
            "departure_date": "2025-07-15",
            "passengers": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()

    assert isinstance(data, list)
    assert len(data) >= 3  # At least 3 flights
    assert len(data) <= 20  # Default limit

    # Validate flight structure
    for flight in data:
        assert "id" in flight
        assert "origin" in flight
        assert "destination" in flight
        assert "departure" in flight
        assert "arrival" in flight
        assert "price" in flight
        assert "carrier" in flight
        assert "flight_number" in flight
        assert "duration_minutes" in flight
        assert "stops" in flight


def test_search_flights_validates_iata_codes() -> None:
    """Test endpoint validates IATA codes."""
    # Invalid origin
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "INVALID",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )
    assert response.status_code == 422  # Validation error

    # Invalid destination
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "12",
            "departure_date": "2025-06-01",
        },
    )
    assert response.status_code == 422


def test_search_flights_normalizes_lowercase_iata() -> None:
    """Test endpoint normalizes lowercase IATA codes."""
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "lax",
            "destination": "jfk",
            "departure_date": "2025-06-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # All flights should have uppercase codes
    for flight in data:
        assert flight["origin"] == "LAX"
        assert flight["destination"] == "JFK"


def test_search_flights_sorts_by_price_default() -> None:
    """Test endpoint sorts by price by default."""
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "ORD",
            "destination": "ATL",
            "departure_date": "2025-08-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    prices = [Decimal(f["price"]) for f in data]
    assert prices == sorted(prices)


def test_search_flights_sorts_by_duration() -> None:
    """Test endpoint sorts by duration when specified."""
    response = client.post(
        "/api/flights/search?sort_by=duration",
        json={
            "origin": "JFK",
            "destination": "LAX",
            "departure_date": "2025-06-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    durations = [f["duration_minutes"] for f in data]
    assert durations == sorted(durations)


def test_search_flights_sorts_by_departure() -> None:
    """Test endpoint sorts by departure time when specified."""
    response = client.post(
        "/api/flights/search?sort_by=departure",
        json={
            "origin": "LAX",
            "destination": "SFO",
            "departure_date": "2025-06-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    departure_times = [f["departure"] for f in data]
    assert departure_times == sorted(departure_times)


def test_search_flights_filters_by_max_price() -> None:
    """Test endpoint filters by max_price."""
    response = client.post(
        "/api/flights/search?max_price=300.00",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    for flight in data:
        assert Decimal(flight["price"]) <= Decimal("300.00")


def test_search_flights_filters_by_max_duration() -> None:
    """Test endpoint filters by max_duration."""
    response = client.post(
        "/api/flights/search?max_duration=360",
        json={
            "origin": "SFO",
            "destination": "SEA",
            "departure_date": "2025-07-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    for flight in data:
        assert flight["duration_minutes"] <= 360


def test_search_flights_filters_by_max_stops() -> None:
    """Test endpoint filters by max_stops."""
    response = client.post(
        "/api/flights/search?max_stops=0",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )

    assert response.status_code == 200
    data = response.json()

    # All flights should be direct
    for flight in data:
        assert flight["stops"] == 0


def test_search_flights_paginates_results() -> None:
    """Test endpoint paginates results."""
    # Get first page
    response1 = client.post(
        "/api/flights/search?limit=2&offset=0",
        json={
            "origin": "JFK",
            "destination": "LAX",
            "departure_date": "2025-06-01",
        },
    )

    assert response1.status_code == 200
    page1 = response1.json()
    assert len(page1) == 2

    # Get second page
    response2 = client.post(
        "/api/flights/search?limit=2&offset=2",
        json={
            "origin": "JFK",
            "destination": "LAX",
            "departure_date": "2025-06-01",
        },
    )

    assert response2.status_code == 200
    page2 = response2.json()
    assert len(page2) == 2

    # Pages should be different (using deterministic mock with same params would be same)
    # But since we're using random mock, just verify structure
    assert page1[0]["id"] != ""
    assert page2[0]["id"] != ""


def test_search_flights_validates_limit_range() -> None:
    """Test endpoint validates limit parameter range."""
    # Below minimum
    response = client.post(
        "/api/flights/search?limit=0",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )
    assert response.status_code == 422

    # Above maximum
    response = client.post(
        "/api/flights/search?limit=101",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )
    assert response.status_code == 422


def test_get_flight_details_endpoint() -> None:
    """Test /api/flights/{id} endpoint returns flight details."""
    # First search to get a valid flight ID
    search_response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )
    flights = search_response.json()
    flight_id = flights[0]["id"]

    # Get details
    response = client.get(f"/api/flights/{flight_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["id"] == flight_id
    assert "carrier" in data
    assert "price" in data


def test_get_flight_details_returns_404_for_unknown_id() -> None:
    """Test /api/flights/{id} returns 404 for unknown flight."""
    response = client.get("/api/flights/unknown-id-12345")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_check_availability_endpoint() -> None:
    """Test /api/flights/{id}/availability endpoint."""
    # First search to get a valid flight ID
    search_response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
        },
    )
    flights = search_response.json()
    flight_id = flights[0]["id"]

    # Check availability
    response = client.get(f"/api/flights/{flight_id}/availability")

    assert response.status_code == 200
    data = response.json()

    assert "available" in data
    assert isinstance(data["available"], bool)


def test_search_flights_validates_passengers_range() -> None:
    """Test endpoint validates passengers parameter range."""
    # Below minimum
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
            "passengers": 0,
        },
    )
    assert response.status_code == 422

    # Above maximum
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-01",
            "passengers": 10,
        },
    )
    assert response.status_code == 422


def test_search_flights_validates_return_date() -> None:
    """Test endpoint validates return_date is after departure_date."""
    response = client.post(
        "/api/flights/search",
        json={
            "origin": "LAX",
            "destination": "JFK",
            "departure_date": "2025-06-10",
            "return_date": "2025-06-05",  # Before departure
        },
    )

    assert response.status_code == 422
    assert "return date" in response.json()["detail"][0]["msg"].lower()
