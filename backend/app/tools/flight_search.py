"""Flight search tool for LangChain agent."""

from collections.abc import Awaitable, Callable
from datetime import date
from decimal import Decimal

from app.domain.models import FlightQuery
from app.exceptions import FlightSearchError
from app.services.flight import FlightService, SortBy


def create_flight_search_tool(service: FlightService) -> Callable[..., Awaitable[str]]:
    """Create flight search tool function with closure over FlightService.

    Args:
        service: FlightService instance for flight operations

    Returns:
        Tool function that can be passed to LangChain agent
    """

    async def search_flights(
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int = 1,
        sort_by: str = "price",
        max_price: float | None = None,
        max_duration: int | None = None,
        max_stops: int | None = None,
        limit: int = 5,
    ) -> str:
        """Search for flights between two airports.

        **When to use this tool:**
        - User asks about flights, airfare, or travel options between cities/airports
        - User wants to compare flight options or find the best flights
        - User requests specific flight information (prices, times, duration, airlines)

        **When NOT to use this tool:**
        - General greetings or small talk ("Hello", "How are you?")
        - Questions about hotels, cars, restaurants, or non-flight travel
        - Already have flight search results and user is just asking follow-up questions about them

        **Handling ambiguous requests:**
        - If city name is provided instead of IATA code, infer the most likely major airport:
          * "Los Angeles" or "LA" → "LAX"
          * "New York" or "NYC" → "JFK"
          * "San Francisco" or "SF" → "SFO"
          * "Chicago" → "ORD"
          * "Miami" → "MIA"
          * "Seattle" → "SEA"
          * "Boston" → "BOS"
        - If origin, destination, or date is missing, ask the user for clarification
        - If date is relative ("tomorrow", "next week"), calculate the actual date based on TODAY'S DATE
        - If user says "flights to X" without origin, ask where they're flying from
        - If date format is wrong (like MM/DD/YYYY), convert it to YYYY-MM-DD

        **Expected output format:**
        - Returns formatted text with up to {limit} flight options
        - Each flight includes: carrier, flight number, times, duration, stops, price, booking class
        - Includes Flight ID for potential future booking reference
        - If no flights found, suggests broadening search criteria

        Args:
            origin: Origin airport IATA code (3 letters, e.g., "LAX", "JFK")
            destination: Destination airport IATA code (3 letters, e.g., "SFO", "ORD")
            departure_date: Departure date in YYYY-MM-DD format (e.g., "2025-06-15")
                          IMPORTANT: Today is November 12, 2025. Use dates in 2025 or 2026.
            passengers: Number of passengers (default: 1, min: 1, max: 9)
            sort_by: Sort results by "price" (default), "duration", or "departure"
            max_price: Optional maximum price filter in USD (e.g., 500.00)
            max_duration: Optional maximum duration filter in minutes (e.g., 360 for 6 hours)
            max_stops: Optional maximum number of stops - 0 (direct only), 1, or 2 (default: no filter)
            limit: Maximum number of results to return (default: 5, max: 20)

        Returns:
            Formatted string with flight options or error message.
            Always returns a string - never raises exceptions to the LLM.
        """
        try:
            # Validate and parse inputs
            try:
                departure_date_obj = date.fromisoformat(departure_date)
            except ValueError as e:
                return f"Error: Invalid date format '{departure_date}'. Please use YYYY-MM-DD format (e.g., '2025-06-15'). Details: {e}"

            # Validate IATA codes (basic check)
            if len(origin) != 3 or not origin.isalpha():
                return f"Error: Invalid origin airport code '{origin}'. Must be 3 letters (e.g., 'LAX')."
            if len(destination) != 3 or not destination.isalpha():
                return f"Error: Invalid destination airport code '{destination}'. Must be 3 letters (e.g., 'JFK')."

            origin = origin.upper()
            destination = destination.upper()

            # Validate sort_by
            valid_sort_by = ["price", "duration", "departure"]
            if sort_by not in valid_sort_by:
                return f"Error: Invalid sort_by '{sort_by}'. Must be 'price', 'duration', or 'departure'."
            sort_by_value: SortBy = sort_by  # type: ignore[assignment]

            # Validate numeric parameters
            if passengers < 1:
                return "Error: Number of passengers must be at least 1."
            if limit < 1 or limit > 20:
                return "Error: Limit must be between 1 and 20."
            if max_stops is not None and (max_stops < 0 or max_stops > 2):
                return "Error: max_stops must be 0 (direct), 1, or 2."
            if max_duration is not None and max_duration < 0:
                return "Error: max_duration must be a positive number of minutes."
            if max_price is not None and max_price <= 0:
                return "Error: max_price must be a positive number."

            # Create query
            query = FlightQuery(
                origin=origin,
                destination=destination,
                departure_date=departure_date_obj,
                passengers=passengers,
            )

            # Convert max_price to Decimal if provided
            max_price_decimal = Decimal(str(max_price)) if max_price is not None else None

            # Search flights
            flights = await service.search_flights(
                query=query,
                sort_by=sort_by_value,
                max_price=max_price_decimal,
                max_duration=max_duration,
                max_stops=max_stops,
                limit=limit,
            )

            if not flights:
                return f"No flights found from {origin} to {destination} on {departure_date} matching your criteria."

            # Format results
            result_lines = [
                f"Found {len(flights)} flight(s) from {origin} to {destination} on {departure_date}:\n"
            ]

            for i, flight in enumerate(flights, 1):
                # Calculate duration in hours and minutes
                hours = flight.duration_minutes // 60
                minutes = flight.duration_minutes % 60
                duration_str = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

                # Format stops
                if flight.stops == 0:
                    stops_str = "Direct"
                elif flight.stops == 1:
                    stops_str = "1 stop"
                else:
                    stops_str = f"{flight.stops} stops"

                # Format times
                departure_time = flight.departure.strftime("%I:%M %p")
                arrival_time = flight.arrival.strftime("%I:%M %p")

                result_lines.append(
                    f"{i}. {flight.carrier} {flight.flight_number}\n"
                    f"   Departs: {departure_time} → Arrives: {arrival_time}\n"
                    f"   Duration: {duration_str} ({stops_str})\n"
                    f"   Price: ${flight.price} {flight.currency} ({flight.booking_class})\n"
                    f"   Flight ID: {flight.id}\n"
                )

            return "\n".join(result_lines)

        except FlightSearchError as e:
            return f"Flight search error: {e}"
        except Exception as e:
            return f"Unexpected error during flight search: {e}"

    # Set function metadata for LangChain
    search_flights.__name__ = "search_flights"

    return search_flights
