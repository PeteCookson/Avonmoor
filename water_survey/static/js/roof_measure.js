(function () {
    'use strict';

    const mapElement = document.getElementById('roof-map');
    const fallbackPanel = document.getElementById('manual-location-fallback');
    if (!mapElement && !fallbackPanel) return;

    const areaInput = document.getElementById('id_area_m2');
    const polygonInput = document.getElementById('id_polygon');
    const latitudeInput = document.getElementById('id_map_latitude');
    const longitudeInput = document.getElementById('id_map_longitude');
    const locationMethodInput = document.getElementById('id_location_method');
    const areaOutput = document.getElementById('map-area');
    const message = document.getElementById('map-message');
    const undoButton = document.getElementById('undo-map-point');
    const clearButton = document.getElementById('clear-map');
    const fallbackButton = document.getElementById('use-postcode-location');
    const fallbackStatus = document.getElementById('postcode-location-status');
    const submitButton = document.getElementById('calculate-submit');
    let map;
    let roofPolygon;
    let mapLoadTimer;

    function hasCoordinates() {
        return (
            latitudeInput &&
            longitudeInput &&
            latitudeInput.value !== '' &&
            longitudeInput.value !== '' &&
            Number.isFinite(Number(latitudeInput.value)) &&
            Number.isFinite(Number(longitudeInput.value))
        );
    }

    function updateSubmitAvailability() {
        if (submitButton) submitButton.disabled = !hasCoordinates();
    }

    function setLocationMethod(method) {
        if (locationMethodInput) locationMethodInput.value = method;
    }

    function setMessage(text, isError) {
        if (!message) return;
        message.textContent = text;
        message.classList.toggle('map-error', Boolean(isError));
    }

    function setFallbackStatus(text, isError) {
        if (!fallbackStatus) return;
        fallbackStatus.textContent = text;
        fallbackStatus.classList.toggle('map-error', Boolean(isError));
    }

    function showManualFallback(reason) {
        if (!fallbackPanel) return;
        fallbackPanel.hidden = false;
        if (reason) setFallbackStatus(reason, false);
    }

    function handleMapFailure(reason) {
        setMessage(
            mapElement.dataset.requiresLocation === 'true'
                ? reason + ' Use the postcode fallback to continue.'
                : reason + ' Enter the roof area manually.',
            true
        );
        showManualFallback(reason + ' You can continue with the postcode fallback.');
    }

    function markManualAreaReady() {
        if (polygonInput) polygonInput.value = '';
        if (areaInput) {
            areaInput.readOnly = false;
            const areaField = areaInput.closest('.area-field');
            if (areaField) areaField.classList.add('manual-area-active');
        }
        if (areaOutput) areaOutput.textContent = 'Manual area';
        if (fallbackPanel) fallbackPanel.classList.add('is-ready');
        updateSubmitAvailability();
    }

    async function usePostcodeLocation() {
        if (!fallbackPanel || !fallbackButton) return;
        const postcode = (fallbackPanel.dataset.postcode || '').trim();
        if (!postcode) {
            setFallbackStatus(
                'No postcode is available. Return to the property step and enter one.',
                true
            );
            return;
        }

        fallbackButton.disabled = true;
        setFallbackStatus('Finding the approximate postcode location…', false);
        try {
            const normalizedPostcode = postcode.replace(/\s+/g, '');
            let latitude;
            let longitude;
            try {
                const localResponse = await fetch(
                    fallbackPanel.dataset.lookupUrl +
                    '?postcode=' + encodeURIComponent(normalizedPostcode),
                    { headers: { Accept: 'application/json' } }
                );
                const localPayload = await localResponse.json();
                latitude = Number(localPayload && localPayload.latitude);
                longitude = Number(localPayload && localPayload.longitude);
                if (
                    !localResponse.ok ||
                    !Number.isFinite(latitude) ||
                    !Number.isFinite(longitude)
                ) {
                    throw new Error('Local postcode lookup failed');
                }
            } catch (localError) {
                const directResponse = await fetch(
                    'https://api.postcodes.io/postcodes/' +
                    encodeURIComponent(normalizedPostcode)
                );
                const directPayload = await directResponse.json();
                const directResult = directPayload && directPayload.result;
                latitude = Number(directResult && directResult.latitude);
                longitude = Number(directResult && directResult.longitude);
                if (
                    !directResponse.ok ||
                    !Number.isFinite(latitude) ||
                    !Number.isFinite(longitude)
                ) {
                    throw new Error('Direct postcode lookup failed');
                }
            }

            if (roofPolygon) roofPolygon.getPath().clear();
            latitudeInput.value = latitude.toFixed(6);
            longitudeInput.value = longitude.toFixed(6);
            setLocationMethod('postcode');
            markManualAreaReady();
            setFallbackStatus(
                'Postcode location ready. Enter the horizontal roof area below.',
                false
            );
            if (areaInput) areaInput.focus();
        } catch (error) {
            setFallbackStatus(
                'The postcode lookup is unavailable. Check the postcode or try again shortly.',
                true
            );
        } finally {
            fallbackButton.disabled = false;
        }
    }

    if (fallbackButton) fallbackButton.addEventListener('click', usePostcodeLocation);
    updateSubmitAvailability();

    if (!mapElement || !mapElement.dataset.apiKey) {
        showManualFallback('Choose the postcode fallback to continue without the map.');
        if (hasCoordinates() && locationMethodInput && locationMethodInput.value === 'postcode') {
            markManualAreaReady();
            setFallbackStatus(
                'Postcode location ready. Enter the horizontal roof area below.',
                false
            );
        }
        return;
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
        if (undoButton) undoButton.disabled = coordinates.length === 0;
        if (clearButton) clearButton.disabled = coordinates.length === 0;

        if (!hasPolygon) {
            polygonInput.value = '';
            areaOutput.textContent = coordinates.length
                ? coordinates.length + ' of 3+ points'
                : 'No outline';
            areaInput.readOnly = false;
            updateSubmitAvailability();
            return;
        }

        const closedCoordinates = coordinates.concat([coordinates[0]]);
        const area = google.maps.geometry.spherical.computeArea(
            roofPolygon.getPath()
        );
        const roofBounds = new google.maps.LatLngBounds();
        roofPolygon.getPath().forEach(function (point) {
            roofBounds.extend(point);
        });
        const roofCentre = roofBounds.getCenter();
        polygonInput.value = JSON.stringify({
            type: 'Polygon',
            coordinates: [closedCoordinates],
        });
        latitudeInput.value = roofCentre.lat().toFixed(6);
        longitudeInput.value = roofCentre.lng().toFixed(6);
        setLocationMethod('map');
        areaInput.value = area.toFixed(2);
        areaInput.readOnly = true;
        const areaField = areaInput.closest('.area-field');
        if (areaField) areaField.classList.remove('manual-area-active');
        areaOutput.textContent = area.toFixed(1) + ' m²';
        setMessage('Outline measured. Drag any point to refine it.', false);
        updateSubmitAvailability();
    }

    function addPoint(event) {
        roofPolygon.getPath().push(event.latLng);
        syncMeasurement();
    }

    function initialisePolygon() {
        roofPolygon = new google.maps.Polygon({
            map: map,
            paths: [[]],
            editable: true,
            clickable: false,
            strokeColor: '#30569A',
            strokeOpacity: 1,
            strokeWeight: 3,
            fillColor: '#51A4CF',
            fillOpacity: 0.32,
        });

        const path = roofPolygon.getPath();
        google.maps.event.addListener(path, 'insert_at', syncMeasurement);
        google.maps.event.addListener(path, 'set_at', syncMeasurement);
        google.maps.event.addListener(path, 'remove_at', syncMeasurement);
        google.maps.event.addListener(map, 'click', addPoint);
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
            updateSubmitAvailability();
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
                    setLocationMethod('map');
                    setMessage('Check the property, then tap around the roof corners.', false);
                    updateSubmitAvailability();
                    return;
                }
                setMessage(
                    'The address could not be located. Move the map manually, or use the postcode fallback.',
                    true
                );
                showManualFallback('The address lookup failed. You can continue with the postcode fallback.');
            }
        );
    }

    window.initAvonmoorRoofMap = function () {
        window.clearTimeout(mapLoadTimer);
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

    window.gm_authFailure = function () {
        window.clearTimeout(mapLoadTimer);
        handleMapFailure('Google Maps could not be authorised.');
    };

    if (undoButton) {
        undoButton.addEventListener('click', function () {
            const path = roofPolygon.getPath();
            if (path.getLength()) path.pop();
        });
    }

    if (clearButton) {
        clearButton.addEventListener('click', function () {
            roofPolygon.getPath().clear();
            areaInput.value = '';
            areaInput.readOnly = false;
            setMessage('Outline cleared. Tap the map to start again.', false);
        });
    }

    const script = document.createElement('script');
    script.src =
        'https://maps.googleapis.com/maps/api/js?key=' +
        encodeURIComponent(mapElement.dataset.apiKey) +
        '&libraries=geometry&loading=async&callback=initAvonmoorRoofMap&v=quarterly';
    script.async = true;
    script.onerror = function () {
        window.clearTimeout(mapLoadTimer);
        handleMapFailure('Google Maps did not load.');
    };
    document.head.appendChild(script);
    mapLoadTimer = window.setTimeout(function () {
        if (!map) handleMapFailure('Google Maps is taking too long to load.');
    }, 10000);
})();
