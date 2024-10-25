// Initialize the map centered in Minnesota
const map = L.map('map').setView([46.7296, -94.6859], 7);

// Add tile layer from OpenStreetMap
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap contributors'
}).addTo(map);

// Heatmap layer
let heatmapLayer;
let routeLayers = [];
let poiMarkers = [];
// Function to decode Google's encoded polyline
function decodePolyline(encoded) {
    const points = [];
    let index = 0, lat = 0, lng = 0;

    while (index < encoded.length) {
        let shift = 0, result = 0;
        
        let byte;
        do {
            byte = encoded.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        
        const dlat = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lat += dlat;

        shift = 0;
        result = 0;
        
        do {
            byte = encoded.charCodeAt(index++) - 63;
            result |= (byte & 0x1f) << shift;
            shift += 5;
        } while (byte >= 0x20);
        
        const dlng = ((result & 1) ? ~(result >> 1) : (result >> 1));
        lng += dlng;

        points.push([lat * 1e-5, lng * 1e-5]);
    }
    return points;
}

// Function to fetch coordinates from Nominatim API
async function getCoordinates(location) {
    const url = `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(location)}&format=json&limit=1`;
    const response = await fetch(url);
    const data = await response.json();

    if (data && data.length > 0) {
        return { name: location, lat: parseFloat(data[0].lat), lon: parseFloat(data[0].lon) };
    } else {
        throw new Error("Location not found");
    }
}

// Handle form submission for source, destination, and user preferences
document.getElementById('locationForm').addEventListener('submit', async function (event) {
    event.preventDefault();

    const source = document.getElementById('source').value;
    const destination = document.getElementById('destination').value;
    const mood = document.getElementById('mood').value;

    const preferredStops = [];
    if (document.getElementById('restaurants').checked) preferredStops.push('restaurants');
    if (document.getElementById('motels').checked) preferredStops.push('motels');
    if (document.getElementById('parks').checked) preferredStops.push('parks');

    try {
        const sourceCoords = await getCoordinates(source);
        const destinationCoords = await getCoordinates(destination);

        console.log("Source coordinates:", sourceCoords);
        console.log("Destination coordinates:", destinationCoords);

        const payload = {
            source: sourceCoords,
            destination: destinationCoords,
            mood: mood,
            preferred_stops: preferredStops
        };

        console.log("Sending payload to /fetch_routes:", payload);
        await fetchRoutes(payload);
    } catch (error) {
        console.error("Error in form submission:", error);
    }
});

// async function fetchRoutes(payload) {
//     try {
//         const response = await fetch('/fetch_routes', {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json'
//             },
//             body: JSON.stringify(payload)
//         });

//         if (!response.ok) {
//             throw new Error(`Failed to fetch routes: ${response.statusText}`);
//         }

//         const data = await response.json();
//         if (data.routes) {
//             console.log("Routes data:", data);

//             // Fetch and display POIs
//             await fetchAndDisplayHeatMap(payload.source, payload.destination);
//             await generateStory(payload);
//         } else {
//             console.error("Error fetching routes:", data.error);
//         }
//     } catch (error) {
//         console.error("Error:", error);
//     }
// }
async function fetchRoutes(payload) {
    try {
        const response = await fetch('/fetch_routes', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch routes: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.routes) {
            // Clear existing routes
            routeLayers.forEach(layer => map.removeLayer(layer));
            routeLayers = [];

            // Display each alternative route
            data.routes.forEach((route, index) => {
                const points = decodePolyline(route.overview_polyline.points);
                const routeColor = index === 0 ? '#0000FF' : '#808080'; // Blue for primary route, gray for alternatives
                
                const routeLine = L.polyline(points, {
                    color: routeColor,
                    weight: 5,
                    opacity: 0.7
                }).addTo(map);

                // Add route information popup
                const duration = route.legs[0].duration.text;
                const distance = route.legs[0].distance.text;
                routeLine.bindPopup(`Route ${index + 1}<br>Distance: ${distance}<br>Duration: ${duration}`);
                
                routeLayers.push(routeLine);
            });

            // Fit map bounds to show all routes
            const bounds = L.latLngBounds(routeLayers[0].getLatLngs());
            routeLayers.forEach(layer => {
                layer.getLatLngs().forEach(latLng => bounds.extend(latLng));
            });
            map.fitBounds(bounds, { padding: [50, 50] });

            // Add markers for source and destination
            const sourceLatLng = [payload.source.lat, payload.source.lon];
            const destLatLng = [payload.destination.lat, payload.destination.lon];

            L.marker(sourceLatLng)
                .addTo(map)
                .bindPopup('Start: ' + payload.source.name);
            
            L.marker(destLatLng)
                .addTo(map)
                .bindPopup('End: ' + payload.destination.name);

            // Fetch and display POIs
            await fetchAndDisplayHeatMap(payload.source, payload.destination);
            await generateStory(payload);
        } else {
            console.error("Error fetching routes:", data.error);
        }
    } catch (error) {
        console.error("Error:", error);
    }
}
async function fetchAndDisplayHeatMap(sourceCoords, destinationCoords) {
    try {
        const response = await fetch('/fetch_pois', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                source: sourceCoords,
                destination: destinationCoords,
                proximity_km: 10
            })
        });

        if (!response.ok) {
            throw new Error(`Failed to fetch POIs: ${response.statusText}`);
        }

        const data = await response.json();
        if (data.pois && data.pois.length > 0) {
            // Clear existing markers
            poiMarkers.forEach(marker => map.removeLayer(marker));
            poiMarkers = [];

            const heatPoints = data.pois.map(poi => [poi.location.lat, poi.location.lon]);

            // Clear existing heatmap layer
            if (heatmapLayer) {
                map.removeLayer(heatmapLayer);
            }

            // Add new heatmap layer
            heatmapLayer = L.heatLayer(heatPoints, { 
                radius: 25,
                minOpacity: 0.4,
                gradient: {0.4: 'blue', 0.65: 'lime', 1: 'red'}
            }).addTo(map);

            // Add clickable markers for each POI
            data.pois.forEach(poi => {
                const marker = L.circleMarker([poi.location.lat, poi.location.lon], {
                    radius: 8,
                    fillColor: '#ff7800',
                    color: '#000',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                })
                .addTo(map)
                .bindPopup(`<b>${poi.name}</b><br>${poi.category}<br><button onclick="generatePoiStory('${poi.name}', '${poi.category}')" class="story-btn">Generate Story</button>`);
                
                marker.on('click', () => {
                    marker.openPopup();
                });

                poiMarkers.push(marker);
            });
        } else {
            console.error('No POIs found');
        }
    } catch (error) {
        console.error('Error fetching POIs:', error);
    }
}
async function generatePoiStory(poiName, poiCategory) {
    try {
        const storyResponse = await fetch('/generate_poi_story', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                poi_name: poiName,
                poi_category: poiCategory
            })
        });

        if (!storyResponse.ok) {
            throw new Error(`Failed to generate story: ${storyResponse.statusText}`);
        }

        const storyData = await storyResponse.json();
        if (storyData && storyData.story) {
            // Display the story in a modal or designated area
            const storyContainer = document.getElementById('story');
            storyContainer.innerHTML = `
                <div class="story-header">
                    <h3>${poiName}</h3>
                    <p class="category-tag">${poiCategory}</p>
                </div>
                <div class="story-content">
                    ${storyData.story}
                </div>
            `;
            storyContainer.style.display = 'block';
        }
    } catch (error) {
        console.error('Error generating story:', error);
        alert('Failed to generate story. Please try again.');
    }
}

// Add CSS styles for the story container
const styles = `
    .story-btn {
        background-color: #4CAF50;
        color: white;
        padding: 5px 10px;
        border: none;
        border-radius: 4px;
        cursor: pointer;
        margin-top: 5px;
    }
    .story-btn:hover {
        background-color: #45a049;
    }
    #story {
        position: fixed;
        right: 20px;
        top: 20px;
        width: 300px;
        max-height: 80vh;
        background-color: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        overflow-y: auto;
        display: none;
    }
    .story-header {
        border-bottom: 1px solid #eee;
        margin-bottom: 10px;
        padding-bottom: 10px;
    }
    .category-tag {
        display: inline-block;
        background-color: #e9ecef;
        padding: 3px 8px;
        border-radius: 12px;
        font-size: 0.9em;
        color: #495057;
    }
`;

// Add styles to document
const styleSheet = document.createElement('style');
styleSheet.textContent = styles;
document.head.appendChild(styleSheet);
