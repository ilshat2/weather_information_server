from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
import httpx
import asyncio
from datetime import datetime, timedelta

app = FastAPI()

# Open-Meteo API URL
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# In-memory storage for cities and weather data
cities = {}
weather_data = {}


class City(BaseModel):
    name: str
    latitude: float
    longitude: float


class WeatherRequest(BaseModel):
    city_name: str
    time: Optional[str] = None
    parameters: List[str] = Query(
        default=[
            "temperature",
            "humidity",
            "wind_speed",
            "precipitation"
            ]
    )


async def fetch_weather(lat: float, lon: float):
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": ["temperature_2m",
                   "humidity_2m",
                   "windspeed_10m",
                   "precipitation"]
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        return response.json()


async def update_weather():
    while True:
        for city_name, city in cities.items():
            weather = await fetch_weather(city["latitude"], city["longitude"])
            weather_data[city_name] = weather
        await asyncio.sleep(15 * 60)  # 15 minutes


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(update_weather())


@app.get("/current-weather/")
async def get_current_weather(latitude: float, longitude: float):
    try:
        weather = await fetch_weather(latitude, longitude)
        current = weather.get("current_weather", {})
        return {
            "temperature": current.get("temperature"),
            "wind_speed": current.get("windspeed"),
            "pressure": current.get("pressure")
        }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Error fetching weather data: {str(e)}")


@app.post("/add-city/")
async def add_city(city: City):
    if city.name in cities:
        raise HTTPException(status_code=400, detail="City already exists.")
    cities[city.name] = {"latitude": city.latitude, "longitude": city.longitude}
    weather = await fetch_weather(city.latitude, city.longitude)
    weather_data[city.name] = weather
    return {"message": f"City {city.name} added successfully."}


@app.get("/cities/")
async def get_cities():
    return list(cities.keys())


@app.post("/weather-by-city/")
async def get_weather_by_city(request: WeatherRequest):
    city_name = request.city_name
    if city_name not in weather_data:
        raise HTTPException(status_code=404, detail="City not found.")
    weather = weather_data[city_name]
    hourly_data = weather.get("hourly", {})

    try:
        if request.time:
            time_index = datetime.strptime(request.time, "%H:%M").hour
        else:
            time_index = datetime.now().hour

        response = {
            param: hourly_data.get(f"{param}_2m")[time_index]
            for param in request.parameters
            if param in hourly_data
        }
        return response

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error processing request: {str(e)}")
