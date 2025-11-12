"""Flight search API endpoints."""

from decimal import Decimal
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.domain.models import Flight, FlightQuery
from app.infrastructure.clients.flight import FlightAPIClient
from app.infrastructure.clients.mock import MockFlightAPIClient
from app.services.flight import FlightService, SortBy

router = APIRouter(prefix="/flights", tags=["flights"])


@lru_cache
def get_flight_client() -> FlightAPIClient:
    """Dependency factory for flight API client.

    Returns:
        FlightAPIClient instance (MockFlightAPIClient for now)

    Note:
        Uses lru_cache to return singleton MockFlightAPIClient to maintain
        consistent flight IDs and cache across requests. Will be replaced
        with real API client in Phase 5.
    """
    return MockFlightAPIClient(seed=42)


def get_flight_service(
    client: Annotated[FlightAPIClient, Depends(get_flight_client)],
) -> FlightService:
    """Dependency factory for flight service.

    Args:
        client: Injected FlightAPIClient

    Returns:
        FlightService instance
    """
    return FlightService(client=client)


@router.post("/search", response_model=list[Flight])
async def search_flights(
    query: FlightQuery,
    service: Annotated[FlightService, Depends(get_flight_service)],
    sort_by: Annotated[
        SortBy, Query(description="Sort by price, duration, or departure")
    ] = "price",
    max_price: Annotated[Decimal | None, Query(description="Maximum price filter")] = None,
    max_duration: Annotated[
        int | None, Query(ge=0, description="Maximum duration in minutes")
    ] = None,
    max_stops: Annotated[
        int | None, Query(ge=0, le=2, description="Maximum number of stops")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Maximum results per page")] = 20,
    offset: Annotated[int, Query(ge=0, description="Number of results to skip")] = 0,
) -> list[Flight]:
    """Search for flights with filtering, sorting, and pagination.

    Args:
        query: Flight search parameters (origin, destination, dates, passengers)
        service: Injected FlightService
        sort_by: Sort criteria (price, duration, departure)
        max_price: Maximum price filter
        max_duration: Maximum duration filter in minutes
        max_stops: Maximum stops filter (0-2)
        limit: Results per page (1-100)
        offset: Results to skip for pagination

    Returns:
        List of flights matching criteria
    """
    return await service.search_flights(
        query=query,
        sort_by=sort_by,
        max_price=max_price,
        max_duration=max_duration,
        max_stops=max_stops,
        limit=limit,
        offset=offset,
    )


@router.get("/{flight_id}", response_model=Flight)
async def get_flight_details(
    flight_id: str,
    service: Annotated[FlightService, Depends(get_flight_service)],
) -> Flight:
    """Get detailed information for a specific flight.

    Args:
        flight_id: Unique flight identifier
        service: Injected FlightService

    Returns:
        Detailed flight information

    Raises:
        HTTPException: 404 if flight not found
    """
    from fastapi import HTTPException

    from app.exceptions import FlightSearchError

    try:
        return await service.get_flight_details(flight_id)
    except FlightSearchError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{flight_id}/availability", response_model=dict[str, bool])
async def check_flight_availability(
    flight_id: str,
    service: Annotated[FlightService, Depends(get_flight_service)],
) -> dict[str, bool]:
    """Check if a flight is still available for booking.

    Args:
        flight_id: Unique flight identifier
        service: Injected FlightService

    Returns:
        Dictionary with 'available' boolean
    """
    available = await service.check_availability(flight_id)
    return {"available": available}
