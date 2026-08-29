(function () {
    'use strict';

    const mapElement = document.getElementById('roof-map');
    if (!mapElement) return;

    const areaInput = document.getElementById('id_area_m2');
    const polygonInput = document.getElementById('id_polygon');
    const latitudeInput = document.getElementById('id_map_latitude');
    const longitudeInput = document.getElementById('id_map_longitude');
    const areaOutput = document.getElementById('map-area');
    const message = document.getElementById('map-message');
    const undoButton = document.getElementById('undo-map-point');
    const clearButton = document.getElementById('clear-map');
    let map;
    let roofPolygon;

    function setMessage(text, isError) {
        message.textContent = text;
        message.classList.toggle('map-error', Boolean(isError));
    }

    function coordinatesFromPath() {
        if (!roofPolygon) return [];
        return roofPolygon.getPath().getArray().map(function (point) {
            return [point.lng(), point.lat()];
        });
    }

    function syncMeasurement() {
        const coordinates = coordinatesFromPath();
        const hasPolygon = coordinates.length >= 3;
        undoButton.disabled = coordinates.length === 0;
        clearButton.disabled = coordinates.length === 0;

        if (!hasPolygon) {
            polygonInput.value = '';
            areaOutput.textContent = coordinates.length
                ? coordinates.length + ' of 3+ points'
                : 'No outline';
            areaInput.readOnly = false;
            return;
        }

        const closedCoordinates = coordinates.concat([coordinates[0]]);
        const area = google.maps.geometry.spherical.computeArea(
            roofPolygon.getPath()
        );
        polygonInput.value = JSON.stringify({
            type: 'Polygon',
            coordinates: [closedCoordinates],
        });
        areaInput.value = area.toFixed(2);
        areaInput.readOnly = true;
        areaOutput.textContent = area.toFixed(1) + ' m²';
        setMessage('Outline measured. Drag any point to refine it.', false);
    }

    function addPoint(event) {
        roofPolygon.getPath().push(event.latLng);
        syncMeasurement();
    }

    function initialisePolygon() {
        roofPolygon = new google.maps.Polygon({
            map: map,
            paths: [],
            editable: true,
            clickable: false,
            strokeColor: '#b66d2b',
            strokeOpacity: 1,
            strokeWeight: 3,
            fillColor: '#d7904f',
            fillOpacity: 0.32,
        });

        const path = roofPolygon.getPath();
        path.addListener('insert_at', syncMeasurement);
        path.addListener('set_at', syncMeasurement);
        path.addListener('remove_at', syncMeasurement);
        map.addListener('click', addPoint);
    }

    function restorePolygon() {
        if (!polygonInput.value) return false;

        try {
            const geometry = JSON.parse(polygonInput.value);
            const ring = geometry.type === 'Polygon' && geometry.coordinates[0];
            if (!ring || ring.length < 4) return false;

            const path = ring.slice(0, -1).map(function (position) {
                return { lat: Number(position[1]), lng: Number(position[0]) };
            });
            roofPolygon.setPath(path);

            const bounds = new google.maps.LatLngBounds();
            path.forEach(function (point) { bounds.extend(point); });
            map.fitBounds(bounds, 60);
            google.maps.event.addListenerOnce(map, 'idle', function () {
                if (map.getZoom() > 21) map.setZoom(21);
            });
            syncMeasurement();
            return true;
        } catch (error) {
            polygonInput.value = '';
            return false;
        }
    }

    function locateProperty() {
        const latitudeValue = mapElement.dataset.latitude;
        const longitudeValue = mapElement.dataset.longitude;
        const latitude = Number(latitudeValue);
        const longitude = Number(longitudeValue);
        if (
            latitudeValue !== '' &&
            longitudeValue !== '' &&
            Number.isFinite(latitude) &&
            Number.isFinite(longitude)
        ) {
            map.setCenter({ lat: latitude, lng: longitude });
            map.setZoom(20);
            latitudeInput.value = latitude.toFixed(6);
            longitudeInput.value = longitude.toFixed(6);
            setMessage('Tap around the roof corners to draw the catchment.', false);
            return;
        }

        const geocoder = new google.maps.Geocoder();
        geocoder.geocode(
            { address: mapElement.dataset.address, region: 'GB' },
            function (results, status) {
                if (status === 'OK' && results[0]) {
                    const location = results[0].geometry.location;
                    map.setCenter(location);
                    map.setZoom(20);
                    latitudeInput.value = location.lat().toFixed(6);
                    longitudeInput.value = location.lng().toFixed(6);
                    setMessage('Check the property, then tap around the roof corners.', false);
                    return;
                }
                setMessage(
                    'The address could not be located. Move the map manually, then draw the roof.',
                    true
                );
            }
        );
    }

    window.initAvonmoorRoofMap = function () {
        map = new google.maps.Map(mapElement, {
            center: { lat: 50.426, lng: -3.834 },
            zoom: 16,
            mapTypeId: 'satellite',
            tilt: 0,
            clickableIcons: false,
            streetViewControl: false,
            mapTypeControl: false,
            fullscreenControl: true,
            gestureHandling: 'greedy',
        });
        initialisePolygon();
        if (!restorePolygon()) locateProperty();
    };

    undoButton.addEventListener('click', function () {
        const path = roofPolygon.getPath();
        if (path.getLength()) path.pop();
    });

    clearButton.addEventListener('click', function () {
        roofPolygon.getPath().clear();
        areaInput.value = '';
        areaInput.readOnly = false;
        setMessage('Outline cleared. Tap the map to start again.', false);
    });

    const script = document.createElement('script');
    script.src =
        'https://maps.googleapis.com/maps/api/js?key=' +
        encodeURIComponent(mapElement.dataset.apiKey) +
        '&libraries=geometry&callback=initAvonmoorRoofMap&v=quarterly';
    script.async = true;
    script.onerror = function () {
        setMessage('Google Maps failed to load. Enter the roof area manually.', true);
    };
    document.head.appendChild(script);
})();
