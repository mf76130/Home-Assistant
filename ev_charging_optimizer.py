# E-Auto Lade-Optimierer
# Speichern unter: config/python_scripts/ev_charging_optimizer.py

def calculate_final_price(spot_price, netznutzung):
    """Berechnet den finalen Strompreis in ct/kWh"""
    netznutzung_ct = float(netznutzung) * 100
    return (float(spot_price))

def parse_spotty_data(spotty_attributes):
    """Extrahiert Preisdaten aus dem Spotty Sensor"""
    prices = []
    try:
        data = spotty_attributes.get('data', [])
        for entry in data:
            prices.append({
                'time': entry.get('start_time', ''),
                'price': float(entry.get('price_per_kwh', 0))
            })
    except Exception as e:
        logger.warning(f"Fehler beim Parsen der Spotty-Daten: {e}")
    return prices

def find_cheapest_slots(prices, netznutzung, hours_needed):
    """Findet die günstigsten zusammenhängenden Zeitslots"""
    if not prices or hours_needed <= 0:
        return []
    
    slots_per_hour = 4
    slots_needed = int(hours_needed * slots_per_hour)
    
    # WICHTIG: Mindestens 1 Slot, auch bei sehr kleinen Mengen
    if slots_needed < 1:
        slots_needed = 1
    
    if slots_needed > len(prices):
        slots_needed = len(prices)
    
    final_prices = []
    for p in prices:
        final_price = calculate_final_price(p['price'], netznutzung)
        final_prices.append({
            'time': p['time'],
            'price': final_price
        })
    
    if len(final_prices) < slots_needed:
        return []
    
    best_slots = []
    best_cost = 999999.0
    
    for i in range(len(final_prices) - slots_needed + 1):
        window = final_prices[i:i + slots_needed]
        total_cost = sum(slot['price'] for slot in window)
        
        if total_cost < best_cost:
            best_cost = total_cost
            best_slots = window
    
    return best_slots

def find_night_charging_slots(prices, netznutzung, hours_needed, end_time_hour=7):
    """Findet Slots für Nachtladung - nur zwischen 22:00 und end_time_hour"""
    if not prices or hours_needed <= 0:
        return []
    
    slots_per_hour = 4
    slots_needed = int(hours_needed * slots_per_hour)
    
    # WICHTIG: Mindestens 1 Slot, auch bei sehr kleinen Mengen
    if slots_needed < 1:
        slots_needed = 1
    
    # NUR Nachtpreise filtern (22:00 - 07:00)
    night_prices = []
    for p in prices:
        try:
            time_str = p['time']
            hour = int(time_str.split('T')[1].split(':')[0])
            
            # Nur Nachtstunden: 22-23 Uhr ODER 0-6 Uhr
            if hour >= 22 or hour < end_time_hour:
                final_price = calculate_final_price(p['price'], netznutzung)
                night_prices.append({
                    'time': time_str,
                    'price': final_price,
                    'hour': hour
                })
        except:
            continue
    
    logger.info(f"Nacht-Preise gefunden: {len(night_prices)} Slots")
    
    if not night_prices or len(night_prices) < slots_needed:
        logger.warning(f"Nicht genug Nacht-Slots: {len(night_prices)} < {slots_needed}")
        return []
    
    best_slots = []
    best_cost = 999999.0
    
    for i in range(len(night_prices) - slots_needed + 1):
        window = night_prices[i:i + slots_needed]
        if len(window) < slots_needed:
            continue
        
        # Prüfe ob das Fenster vor end_time_hour endet
        last_hour = window[-1]['hour']
        
        # Wenn letzter Slot >= 22 Uhr ist, ist es OK (Nacht des gleichen Tages)
        # Wenn letzter Slot < end_time_hour ist, ist es OK (früher Morgen)
        # Wenn letzter Slot zwischen end_time_hour und 22 ist, NICHT OK
        if end_time_hour <= last_hour < 22:
            continue
        
        total_cost = sum(slot['price'] for slot in window)
        
        if total_cost < best_cost:
            best_cost = total_cost
            best_slots = window
    
    return best_slots

def find_day_charging_slots(prices, netznutzung, hours_needed, start_hour=8, end_hour=20):
    """Findet Slots für Tagladung zwischen start_hour und end_hour"""
    if not prices or hours_needed <= 0:
        return []
    
    slots_per_hour = 4
    slots_needed = int(hours_needed * slots_per_hour)
    
    # WICHTIG: Mindestens 1 Slot, auch bei sehr kleinen Mengen
    if slots_needed < 1:
        slots_needed = 1
    
    day_prices = []
    for p in prices:
        try:
            time_str = p['time']
            hour = int(time_str.split('T')[1].split(':')[0])
            if start_hour <= hour < end_hour:
                final_price = calculate_final_price(p['price'], netznutzung)
                day_prices.append({
                    'time': time_str,
                    'price': final_price
                })
        except:
            continue
    
    logger.info(f"Tag-Preise gefunden: {len(day_prices)} Slots")
    
    if len(day_prices) < slots_needed:
        logger.warning(f"Nicht genug Tag-Slots: {len(day_prices)} < {slots_needed}")
        return []
    
    best_slots = []
    best_cost = 999999.0
    
    for i in range(len(day_prices) - slots_needed + 1):
        window = day_prices[i:i + slots_needed]
        total_cost = sum(slot['price'] for slot in window)
        
        if total_cost < best_cost:
            best_cost = total_cost
            best_slots = window
    
    return best_slots

def safe_float(value, default=0.0):
    """Sicheres Konvertieren zu Float"""
    try:
        if value is None or value == 'unknown' or value == 'unavailable':
            return default
        return float(value)
    except:
        return default

def safe_get_attribute(attributes, key, default=0.0):
    """Sicheres Auslesen von Attributen"""
    try:
        value = attributes.get(key, default)
        return safe_float(value, default)
    except:
        return default

def clean_attributes(attr_dict):
    """Entfernt alle None-Werte aus dem Attribute-Dictionary"""
    cleaned = {}
    for key, value in attr_dict.items():
        if value is None:
            # Setze default-Werte basierend auf dem Key-Namen
            if 'start' in key or 'end' in key:
                cleaned[key] = 'N/A'
            elif isinstance(value, bool) or key in ['should_charge', 'should_use', 'wait_for_sun', 'night_calculation_active']:
                cleaned[key] = False
            elif isinstance(value, str) or key in ['charging_car', 'using_car', 'charging_vehicle', 'using_vehicle', 'scenario', 'best_scenario']:
                cleaned[key] = ''
            else:
                cleaned[key] = 0.0
        else:
            cleaned[key] = value
    return cleaned

# Hauptlogik
try:
    logger.info("=== E-Auto Optimizer startet ===")
    
    # Hole aktuelle Zeit für last_update
    try:
        time_state = hass.states.get('sensor.time')
        if time_state:
            current_time = time_state.state
        else:
            current_time = "unknown"
    except:
        current_time = "unknown"
    
    # Fahrzeugdaten einlesen
    tesla_state = hass.states.get('sensor.tesla_batterie_maximale_aufladung')
    zoe_state = hass.states.get('sensor.zoe_batterie_maximale_aufladung')
    tesla_range_state = hass.states.get('sensor.range')
    zoe_range_state = hass.states.get('sensor.batterieautonomie')
    
    if not all([tesla_state, zoe_state, tesla_range_state, zoe_range_state]):
        logger.error("Ein oder mehrere Fahrzeug-Sensoren nicht verfügbar")
        tesla_capacity = 0.0
        zoe_capacity = 0.0
        tesla_range = 0.0
        zoe_range = 0.0
    else:
        tesla_capacity = safe_float(tesla_state.state)
        zoe_capacity = safe_float(zoe_state.state)
        tesla_range = safe_float(tesla_range_state.state)
        zoe_range = safe_float(zoe_range_state.state)
    
    logger.info(f"Tesla: {tesla_capacity} kWh, {tesla_range} km")
    logger.info(f"Zoe: {zoe_capacity} kWh, {zoe_range} km")
    
    # Strompreise und PV-Daten
    spotty_state = hass.states.get('sensor.spotty_15_future')  # Korrekt!
    pv_today_state = hass.states.get('sensor.solcast_pv_forecast_prognose_heute')
    pv_tomorrow_state = hass.states.get('sensor.solcast_pv_forecast_prognose_morgen')
    netznutzung_state = hass.states.get('input_number.netznutzungsentgelt')
    
    if not netznutzung_state:
        logger.warning("Netznutzungsentgelt nicht gefunden, verwende 0")
        netznutzung = 0.0
    else:
        netznutzung = safe_float(netznutzung_state.state)
    
    # Parse Spotty Daten
    prices = []
    if spotty_state and spotty_state.attributes:
        prices = parse_spotty_data(spotty_state.attributes)
        logger.info(f"Preisdaten geladen: {len(prices)} Einträge")
        if prices and len(prices) > 0:
            try:
                logger.info(f"Erster Preis: {prices[0]['time']}")
                logger.info(f"Letzter Preis: {prices[-1]['time']}")
            except (IndexError, KeyError) as e:
                logger.warning(f"Fehler beim Loggen der Preisdaten: {e}")
    
    if not prices:
        logger.warning("Keine Preisdaten verfügbar")
    
    # PV Berechnung
    try:
        time_state = hass.states.get('sensor.time')
        if time_state and time_state.state:
            current_hour = int(time_state.state.split(':')[0])
        else:
            current_hour = 12
    except:
        current_hour = 12
    
    pv_today_kwh = 0.0
    pv_tomorrow_kwh = 0.0
    
    if current_hour < 16 and pv_today_state and pv_today_state.attributes:
        pv_today_kwh = safe_get_attribute(pv_today_state.attributes, 'Estimate10', 0.0)
        if pv_today_kwh == 0.0:
            pv_today_kwh = safe_get_attribute(pv_today_state.attributes, 'estimate10', 0.0)
    
    if pv_tomorrow_state and pv_tomorrow_state.attributes:
        pv_tomorrow_kwh = safe_get_attribute(pv_tomorrow_state.attributes, 'Estimate10', 0.0)
        if pv_tomorrow_kwh == 0.0:
            pv_tomorrow_kwh = safe_get_attribute(pv_tomorrow_state.attributes, 'estimate10', 0.0)
    
    pv_total = pv_today_kwh + pv_tomorrow_kwh
    usable_pv = pv_total * 0.7
    
    logger.info(f"PV: Heute {pv_today_kwh} kWh, Morgen {pv_tomorrow_kwh} kWh, Nutzbar {usable_pv} kWh")
    logger.info(f"Aktuelle Stunde: {current_hour}")
    
    # ═══════════════════════════════════════════════════════════════════
    # VERBESSERTE ENTSCHEIDUNGSLOGIK
    # ═══════════════════════════════════════════════════════════════════
    charge_tesla = False
    charge_zoe = False
    use_tesla = False
    use_zoe = False
    
    # Schwellenwerte für intelligente Entscheidung
    MIN_CAPACITY_THRESHOLD = 5.0  # kWh - unter diesem Wert ist es "fast voll"
    SIGNIFICANT_DIFFERENCE = 10.0  # kWh - ab diesem Unterschied hat ein Auto deutlich mehr Bedarf
    
    if tesla_capacity <= 0 and zoe_capacity <= 0:
        # Beide voll
        charge_tesla = False
        charge_zoe = False
        use_tesla = True
        use_zoe = False
    elif tesla_capacity <= 0:
        # Tesla voll, Zoe braucht Ladung
        charge_tesla = False
        charge_zoe = True
        use_tesla = True
        use_zoe = False
    elif zoe_capacity <= 0:
        # Zoe voll, Tesla braucht Ladung
        charge_tesla = True
        charge_zoe = False
        use_tesla = False
        use_zoe = True
    else:
        # Beide brauchen Ladung - intelligente Entscheidung
        capacity_diff = abs(tesla_capacity - zoe_capacity)
        
        # Fall 1: Großer Unterschied in der benötigten Kapazität
        if capacity_diff >= SIGNIFICANT_DIFFERENCE:
            if tesla_capacity > zoe_capacity:
                # Tesla braucht deutlich mehr → Tesla laden
                charge_tesla = True
                charge_zoe = False
                use_tesla = False
                use_zoe = True
                logger.info(f"📊 Entscheidung: Tesla laden (benötigt {tesla_capacity:.1f} kWh vs. Zoe {zoe_capacity:.1f} kWh)")
            else:
                # Zoe braucht deutlich mehr → Zoe laden
                charge_tesla = False
                charge_zoe = True
                use_tesla = True
                use_zoe = False
                logger.info(f"📊 Entscheidung: Zoe laden (benötigt {zoe_capacity:.1f} kWh vs. Tesla {tesla_capacity:.1f} kWh)")
        
        # Fall 2: Ein Auto ist fast voll (< 5 kWh), das andere nicht
        elif tesla_capacity < MIN_CAPACITY_THRESHOLD and zoe_capacity >= MIN_CAPACITY_THRESHOLD:
            # Tesla fast voll, Zoe braucht mehr → Zoe laden
            charge_tesla = False
            charge_zoe = True
            use_tesla = True
            use_zoe = False
            logger.info(f"📊 Entscheidung: Zoe laden (Tesla fast voll mit {tesla_capacity:.1f} kWh)")
        elif zoe_capacity < MIN_CAPACITY_THRESHOLD and tesla_capacity >= MIN_CAPACITY_THRESHOLD:
            # Zoe fast voll, Tesla braucht mehr → Tesla laden
            charge_tesla = True
            charge_zoe = False
            use_tesla = False
            use_zoe = True
            logger.info(f"📊 Entscheidung: Tesla laden (Zoe fast voll mit {zoe_capacity:.1f} kWh)")
        
        # Fall 3: Ähnlicher Bedarf → Entscheidung basierend auf Reichweite
        else:
            if tesla_range < zoe_range:
                # Tesla hat weniger Reichweite → Tesla laden
                charge_tesla = True
                charge_zoe = False
                use_tesla = False
                use_zoe = True
                logger.info(f"📊 Entscheidung: Tesla laden (Reichweite: Tesla {tesla_range:.0f} km < Zoe {zoe_range:.0f} km)")
            else:
                # Zoe hat weniger Reichweite → Zoe laden
                charge_tesla = False
                charge_zoe = True
                use_tesla = True
                use_zoe = False
                logger.info(f"📊 Entscheidung: Zoe laden (Reichweite: Zoe {zoe_range:.0f} km ≤ Tesla {tesla_range:.0f} km)")
    
    charging_car = 'Tesla' if charge_tesla else ('Zoe' if charge_zoe else 'Keines')
    using_car = 'Tesla' if use_tesla else ('Zoe' if use_zoe else 'Beliebig')
    
    logger.info(f"Entscheidung: Laden={charging_car}, Fahren={using_car}")
    # ═══════════════════════════════════════════════════════════════════
    
    # Ladezeiten berechnen
    charging_power = 11.0
    
    tesla_capacity_90 = tesla_capacity * 0.9
    zoe_capacity_90 = zoe_capacity * 0.9
    
    tesla_hours = tesla_capacity / charging_power if tesla_capacity > 0 else 0
    zoe_hours = zoe_capacity / charging_power if zoe_capacity > 0 else 0
    
    tesla_hours_90 = tesla_capacity_90 / charging_power if tesla_capacity_90 > 0 else 0
    zoe_hours_90 = zoe_capacity_90 / charging_power if zoe_capacity_90 > 0 else 0
    
    # Prüfe ob Nachtwerte berechnet werden sollen (nur nach 15:10 Uhr)
    calculate_night = True
    try:
        if time_state and time_state.state and ':' in str(time_state.state):
            current_minute = int(time_state.state.split(':')[1])
        else:
            current_minute = 0
            
        if current_hour < 15 or (current_hour == 15 and current_minute < 10):
            calculate_night = False
            logger.info(f"⏰ Nachtberechnung übersprungen (Zeit: {current_hour}:{current_minute:02d}, benötigt: nach 15:10)")
        else:
            logger.info(f"✓ Nachtberechnung aktiv (Zeit: {current_hour}:{current_minute:02d})")
    except Exception as e:
        calculate_night = False
        logger.warning(f"Konnte Zeit nicht prüfen ({e}), überspringe Nachtberechnung")
    
    # Szenarien berechnen
    tesla_slots_flex = []
    tesla_slots_night = []
    tesla_slots_day = []
    zoe_slots_flex = []
    zoe_slots_night = []
    zoe_slots_day = []
    
    if charge_tesla and prices:
        logger.info(f"Berechne Tesla Slots (benötigt {tesla_hours:.2f}h / {tesla_hours_90:.2f}h)")
        tesla_slots_flex = find_cheapest_slots(prices, netznutzung, tesla_hours)
        if calculate_night:
            tesla_slots_night = find_night_charging_slots(prices, netznutzung, tesla_hours_90, 7)
        tesla_slots_day = find_day_charging_slots(prices, netznutzung, tesla_hours, 8, 20)
        logger.info(f"Tesla Slots: Flex={len(tesla_slots_flex)}, Night={len(tesla_slots_night)}, Day={len(tesla_slots_day)}")
    elif charge_zoe and prices:
        logger.info(f"Berechne Zoe Slots (benötigt {zoe_hours:.2f}h / {zoe_hours_90:.2f}h)")
        zoe_slots_flex = find_cheapest_slots(prices, netznutzung, zoe_hours)
        if calculate_night:
            zoe_slots_night = find_night_charging_slots(prices, netznutzung, zoe_hours_90, 7)
        zoe_slots_day = find_day_charging_slots(prices, netznutzung, zoe_hours, 8, 20)
        logger.info(f"Zoe Slots: Flex={len(zoe_slots_flex)}, Night={len(zoe_slots_night)}, Day={len(zoe_slots_day)}")
    
    # Kosten berechnen
    def calc_avg_cost(slots, capacity):
        if not slots or capacity <= 0:
            return 0.0, 0.0, 0.0, 0.0  # avg_price, cost, raw_spot_price, max_spot_price
        avg_price = sum(slot['price'] for slot in slots) / len(slots)
        cost = (avg_price / 100.0) * capacity
        netznutzung_ct = netznutzung * 100
        raw_spot_price = avg_price
        
        # Finde maximalen Spot-Preis im Zeitfenster
        max_final_price = max(slot['price'] for slot in slots)
        max_spot_price = max_final_price
        
        return avg_price, cost, raw_spot_price, max_spot_price
    
    tesla_price_flex = 0.0
    tesla_cost_flex = 0.0
    tesla_spot_flex = 0.0
    tesla_spot_max_flex = 0.0
    tesla_price_night = 0.0
    tesla_cost_night = 0.0
    tesla_spot_night = 0.0
    tesla_spot_max_night = 0.0
    tesla_price_day = 0.0
    tesla_cost_day = 0.0
    tesla_spot_day = 0.0
    tesla_spot_max_day = 0.0
    
    zoe_price_flex = 0.0
    zoe_cost_flex = 0.0
    zoe_spot_flex = 0.0
    zoe_spot_max_flex = 0.0
    zoe_price_night = 0.0
    zoe_cost_night = 0.0
    zoe_spot_night = 0.0
    zoe_spot_max_night = 0.0
    zoe_price_day = 0.0
    zoe_cost_day = 0.0
    zoe_spot_day = 0.0
    zoe_spot_max_day = 0.0
    
    if charge_tesla:
        if tesla_slots_flex:
            tesla_price_flex, tesla_cost_flex, tesla_spot_flex, tesla_spot_max_flex = calc_avg_cost(tesla_slots_flex, tesla_capacity)
        if tesla_slots_night:
            tesla_price_night, tesla_cost_night, tesla_spot_night, tesla_spot_max_night = calc_avg_cost(tesla_slots_night, tesla_capacity_90)
        if tesla_slots_day:
            tesla_price_day, tesla_cost_day, tesla_spot_day, tesla_spot_max_day = calc_avg_cost(tesla_slots_day, tesla_capacity)
    elif charge_zoe:
        if zoe_slots_flex:
            zoe_price_flex, zoe_cost_flex, zoe_spot_flex, zoe_spot_max_flex = calc_avg_cost(zoe_slots_flex, zoe_capacity)
        if zoe_slots_night:
            zoe_price_night, zoe_cost_night, zoe_spot_night, zoe_spot_max_night = calc_avg_cost(zoe_slots_night, zoe_capacity_90)
        if zoe_slots_day:
            zoe_price_day, zoe_cost_day, zoe_spot_day, zoe_spot_max_day = calc_avg_cost(zoe_slots_day, zoe_capacity)
    
    # PV-Einsparungen
    pv_for_charging = 0.0
    if charge_tesla:
        pv_for_charging = min(tesla_capacity, usable_pv)
    elif charge_zoe:
        pv_for_charging = min(zoe_capacity, usable_pv)
    
    tesla_cost_day_with_pv = 0.0
    zoe_cost_day_with_pv = 0.0
    
    if charge_tesla and tesla_slots_day:
        grid_kwh = max(0, tesla_capacity - pv_for_charging)
        tesla_cost_day_with_pv = (tesla_price_day / 100.0) * grid_kwh
    elif charge_zoe and zoe_slots_day:
        grid_kwh = max(0, zoe_capacity - pv_for_charging)
        zoe_cost_day_with_pv = (zoe_price_day / 100.0) * grid_kwh
    
    # Zeitformatierung - MIT BESSERER FEHLERBEHANDLUNG
    def format_time(slots):
        if not slots or len(slots) == 0:
            return 'N/A', 'N/A'
        try:
            start = slots[0]['time'].split('T')[1][:5]
            end = slots[-1]['time'].split('T')[1][:5]
            return start, end
        except Exception as e:
            logger.warning(f"Fehler beim Formatieren der Zeit: {e}")
            return 'N/A', 'N/A'
    
    tesla_start_flex, tesla_end_flex = format_time(tesla_slots_flex)
    tesla_start_night, tesla_end_night = format_time(tesla_slots_night)
    tesla_start_day, tesla_end_day = format_time(tesla_slots_day)
    
    zoe_start_flex, zoe_end_flex = format_time(zoe_slots_flex)
    zoe_start_night, zoe_end_night = format_time(zoe_slots_night)
    zoe_start_day, zoe_end_day = format_time(zoe_slots_day)
    
    # Sensoren erstellen - stelle sicher dass state nie None ist
    tesla_state_value = round(tesla_cost_flex, 2) if tesla_cost_flex is not None else 0.0
    tesla_attributes = clean_attributes({
        'unit_of_measurement': '€',
        'friendly_name': 'Tesla Ladekosten',
        'capacity_kwh': round(tesla_capacity, 2) if tesla_capacity else 0.0,
        'hours_needed': round(tesla_hours, 2) if tesla_hours else 0.0,
        'current_range': round(tesla_range, 2) if tesla_range else 0.0,
        'should_charge': charge_tesla,
        'should_use': use_tesla,
        'flex_start': tesla_start_flex,
        'flex_end': tesla_end_flex,
        'flex_price_ct': round(tesla_price_flex, 2) if tesla_price_flex else 0.0,
        'flex_cost': round(tesla_cost_flex, 2) if tesla_cost_flex else 0.0,
        'flex_spot_price': round(tesla_spot_flex, 2) if tesla_spot_flex else 0.0,
        'night_start': tesla_start_night,
        'night_end': tesla_end_night,
        'night_price_ct': round(tesla_price_night, 2) if tesla_price_night else 0.0,
        'night_cost': round(tesla_cost_night, 2) if tesla_cost_night else 0.0,
        'night_spot_price': round(tesla_spot_night, 2) if tesla_spot_night else 0.0,
        'night_capacity': round(tesla_capacity_90, 2) if tesla_capacity_90 else 0.0,
        'day_start': tesla_start_day,
        'day_end': tesla_end_day,
        'day_price_ct': round(tesla_price_day, 2) if tesla_price_day else 0.0,
        'day_cost': round(tesla_cost_day, 2) if tesla_cost_day else 0.0,
        'day_spot_price': round(tesla_spot_day, 2) if tesla_spot_day else 0.0,
        'day_cost_with_pv': round(tesla_cost_day_with_pv, 2) if tesla_cost_day_with_pv else 0.0,
        'pv_potential_kwh': round(pv_for_charging if charge_tesla else 0, 2)
    })
    hass.states.set('sensor.ev_optimizer_tesla_cost', tesla_state_value, tesla_attributes)
    
    zoe_state_value = round(zoe_cost_flex, 2) if zoe_cost_flex is not None else 0.0
    zoe_attributes = clean_attributes({
        'unit_of_measurement': '€',
        'friendly_name': 'Zoe Ladekosten',
        'capacity_kwh': round(zoe_capacity, 2) if zoe_capacity else 0.0,
        'hours_needed': round(zoe_hours, 2) if zoe_hours else 0.0,
        'current_range': round(zoe_range, 2) if zoe_range else 0.0,
        'should_charge': charge_zoe,
        'should_use': use_zoe,
        'flex_start': zoe_start_flex,
        'flex_end': zoe_end_flex,
        'flex_price_ct': round(zoe_price_flex, 2) if zoe_price_flex else 0.0,
        'flex_cost': round(zoe_cost_flex, 2) if zoe_cost_flex else 0.0,
        'flex_spot_price': round(zoe_spot_flex, 2) if zoe_spot_flex else 0.0,
        'night_start': zoe_start_night,
        'night_end': zoe_end_night,
        'night_price_ct': round(zoe_price_night, 2) if zoe_price_night else 0.0,
        'night_cost': round(zoe_cost_night, 2) if zoe_cost_night else 0.0,
        'night_spot_price': round(zoe_spot_night, 2) if zoe_spot_night else 0.0,
        'night_capacity': round(zoe_capacity_90, 2) if zoe_capacity_90 else 0.0,
        'day_start': zoe_start_day,
        'day_end': zoe_end_day,
        'day_price_ct': round(zoe_price_day, 2) if zoe_price_day else 0.0,
        'day_cost': round(zoe_cost_day, 2) if zoe_cost_day else 0.0,
        'day_spot_price': round(zoe_spot_day, 2) if zoe_spot_day else 0.0,
        'day_cost_with_pv': round(zoe_cost_day_with_pv, 2) if zoe_cost_day_with_pv else 0.0,
        'pv_potential_kwh': round(pv_for_charging if charge_zoe else 0, 2)
    })
    hass.states.set('sensor.ev_optimizer_zoe_cost', zoe_state_value, zoe_attributes)
    
    # Gesamtkosten - sichere Werte
    total_flex = tesla_cost_flex if charge_tesla else zoe_cost_flex
    total_night = tesla_cost_night if charge_tesla else zoe_cost_night
    total_day = tesla_cost_day if charge_tesla else zoe_cost_day
    total_day_with_pv = tesla_cost_day_with_pv if charge_tesla else zoe_cost_day_with_pv
    
    # Stelle sicher dass keine None-Werte existieren
    total_flex = total_flex if total_flex is not None else 0.0
    total_night = total_night if total_night is not None else 0.0
    total_day = total_day if total_day is not None else 0.0
    total_day_with_pv = total_day_with_pv if total_day_with_pv is not None else 0.0
    
    # Spot-Preise für go-e Charger - sichere Werte
    spot_flex = tesla_spot_flex if charge_tesla else zoe_spot_flex
    spot_night = tesla_spot_night if charge_tesla else zoe_spot_night
    spot_day = tesla_spot_day if charge_tesla else zoe_spot_day
    spot_max_night = tesla_spot_max_night if charge_tesla else zoe_spot_max_night
    spot_max_day = tesla_spot_max_day if charge_tesla else zoe_spot_max_day
    
    # Stelle sicher dass keine None-Werte existieren
    spot_flex = spot_flex if spot_flex is not None else 0.0
    spot_night = spot_night if spot_night is not None else 0.0
    spot_day = spot_day if spot_day is not None else 0.0
    spot_max_night = spot_max_night if spot_max_night is not None else 0.0
    spot_max_day = spot_max_day if spot_max_day is not None else 0.0
    
    # Finde besten Spot-Preis für go-e Charger - MIT FEHLERBEHANDLUNG
    valid_spots = []
    if spot_flex > 0:
        valid_spots.append(('flex', spot_flex, total_flex))
    if spot_night > 0:
        valid_spots.append(('night', spot_night, total_night))
    if spot_day > 0:
        valid_spots.append(('day', spot_day, total_day_with_pv))
    
    if valid_spots:
        try:
            best_scenario, best_spot, best_total = min(valid_spots, key=lambda x: x[2])
        except Exception as e:
            logger.error(f"Fehler beim Finden des besten Spots: {e}")
            best_scenario = 'error'
            best_spot = 0.0
            best_total = 0.0
    else:
        best_scenario = 'none'
        best_spot = 0.0
        best_total = 0.0
    
    total_cost_state = round(total_flex, 2) if total_flex is not None else 0.0
    total_cost_attributes = clean_attributes({
        'unit_of_measurement': '€',
        'friendly_name': 'Ladekosten',
        'charging_car': charging_car,
        'using_car': using_car,
        'total_kwh': round(tesla_capacity if charge_tesla else zoe_capacity, 2) if (tesla_capacity if charge_tesla else zoe_capacity) else 0.0,
        'flex_total': round(total_flex, 2) if total_flex else 0.0,
        'flex_spot_price': round(spot_flex, 2) if spot_flex else 0.0,
        'night_total': round(total_night, 2) if total_night else 0.0,
        'night_spot_price': round(spot_night, 2) if spot_night else 0.0,
        'night_spot_max': round(spot_max_night, 2) if spot_max_night else 0.0,
        'night_kwh': round(tesla_capacity_90 if charge_tesla else zoe_capacity_90, 2) if (tesla_capacity_90 if charge_tesla else zoe_capacity_90) else 0.0,
        'day_total': round(total_day, 2) if total_day else 0.0,
        'day_spot_price': round(spot_day, 2) if spot_day else 0.0,
        'day_spot_max': round(spot_max_day, 2) if spot_max_day else 0.0,
        'day_total_with_pv': round(total_day_with_pv, 2) if total_day_with_pv is not None else 0.0,
        'day_savings': round(total_day - total_day_with_pv, 2) if (total_day and total_day_with_pv is not None) else 0.0,
        'pv_total_kwh': round(usable_pv, 2) if usable_pv else 0.0,
        'pv_used_for_charging': round(pv_for_charging, 2) if pv_for_charging else 0.0,
        'best_spot_price': round(best_spot, 2) if best_spot else 0.0,
        'best_scenario': best_scenario
    })
    hass.states.set('sensor.ev_optimizer_total_cost', total_cost_state, total_cost_attributes)
    
    # Spezieller Sensor für go-e Charger Max Price - sicherer State-Wert
    goe_max_price_state = round(best_spot, 2) if best_spot is not None else 0.0
    goe_attributes = clean_attributes({
        'unit_of_measurement': 'ct/kWh',
        'friendly_name': 'go-e Charger Max Preis',
        'device_class': 'monetary',
        'scenario': best_scenario,
        'charging_car': charging_car,
        'flex_spot': round(spot_flex, 2) if spot_flex else 0.0,
        'night_spot': round(spot_night, 2) if spot_night else 0.0,
        'day_spot': round(spot_day, 2) if spot_day else 0.0
    })
    hass.states.set('sensor.ev_optimizer_goe_max_price', goe_max_price_state, goe_attributes)
    
    # Empfehlung generieren
    short_summary = ""
    
    # PV-Analyse für intelligente Empfehlung
    pv_recommendation = ""
    wait_for_sun = False
    
    # Wenn morgen deutlich mehr PV als heute (>30 kWh morgen, <20 kWh heute)
    if pv_tomorrow_kwh > 30 and pv_today_kwh < 20 and current_hour < 16:
        wait_for_sun = True
        pv_recommendation = "\n\n⚠️ EMPFEHLUNG: Warte bis morgen!\nMorgen: {0} kWh Sonne ☀️\nSpart ca. {1}€ durch PV-Ladung".format(
            round(pv_tomorrow_kwh, 1),
            round((pv_tomorrow_kwh * 0.7 * 0.12), 2)
        )
    
    if not charge_tesla and not charge_zoe:
        state_summary = "✅ Beide Autos voll geladen!"
        short_summary = "🔋 Guten Morgen!\n\n✅ Beide Autos voll!\n\n🚗 Tesla: {0} km\n🚗 Zoe: {1} km\n\n💡 Beliebiges Auto fahren".format(
            int(tesla_range),
            int(zoe_range)
        )
        recommendation_full = """🔋 E-Auto Status

━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ BEIDE AUTOS VOLL GELADEN!
━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚗 Tesla: {0} km Reichweite
🚗 Zoe: {1} km Reichweite

💡 Kein Laden erforderlich
Sie können beliebig wählen!""".format(
            int(tesla_range),
            int(zoe_range)
        )
    else:
        car_name = 'Tesla' if charge_tesla else 'Zoe'
        car_capacity = tesla_capacity if charge_tesla else zoe_capacity
        car_capacity_90 = tesla_capacity_90 if charge_tesla else zoe_capacity_90
        car_range = tesla_range if charge_tesla else zoe_range
        
        other_car = 'Zoe' if charge_tesla else 'Tesla'
        other_range = zoe_range if charge_tesla else tesla_range
        other_capacity = zoe_capacity if charge_tesla else tesla_capacity
        
        # Kurze Zusammenfassung für den Morgen
        short_summary = "🔋 Guten Morgen!\n\n🔌 LADEN: {0}\n   {1} kWh | {2} km\n\n🚙 FAHREN: {3}\n   {4} km Reichweite\n   {5} kWh Lademenge{6}".format(
            car_name,
            round(car_capacity, 1),
            int(car_range),
            other_car,
            int(other_range),
            round(other_capacity, 1),
            pv_recommendation
        )
        
        start_flex = tesla_start_flex if charge_tesla else zoe_start_flex
        end_flex = tesla_end_flex if charge_tesla else zoe_end_flex
        start_night = tesla_start_night if charge_tesla else zoe_start_night
        end_night = tesla_end_night if charge_tesla else zoe_end_night
        start_day = tesla_start_day if charge_tesla else zoe_start_day
        end_day = tesla_end_day if charge_tesla else zoe_end_day
        
        # Sichere Berechnung des besten Preises
        valid_costs = [c for c in [total_flex, total_night, total_day_with_pv] if c > 0]
        best_cost = min(valid_costs) if valid_costs else 0
        
        state_summary = "Laden: {0} | Fahren: {1} | Beste Option: {2}€".format(charging_car, using_car, round(best_cost, 2))
        
        recommendation_full = """🔋 E-Auto Ladeempfehlung

🚗 FAHRZEUG-EMPFEHLUNG

🔌 LADEN: {0}
   ({1} kWh benötigt)
   Aktuelle Reichweite: {2} km

🚙 FAHREN: {3}
   Reichweite: {4} km
   ({5} kWh benötigt)

📊 LADE-SZENARIEN

""".format(
            car_name,
            round(car_capacity, 1),
            int(car_range),
            other_car,
            int(other_range),
            round(other_capacity, 1)
        )
        
        # Nur verfügbare Szenarien anzeigen
        if total_flex > 0:
            recommendation_full += """💡 FLEXIBEL (günstigste Zeit):
   Zeit: {0}-{1} Uhr
   Ladung: {2} kWh (100%)
   Kosten: {3} €
   🔧 go-e Max: {4} ct/kWh

""".format(start_flex, end_flex, round(car_capacity, 1), round(total_flex, 2), round(spot_flex, 2))
        
        if total_night > 0 and calculate_night:
            recommendation_full += """🌙 NACHT (bis 7:00):
   Zeit: {0}-{1} Uhr
   Ladung: {2} kWh (90%)
   Kosten: {3} €
   🔧 go-e Max: {4} ct/kWh

""".format(start_night, end_night, round(car_capacity_90, 1), round(total_night, 2), round(spot_night, 2))
        elif not calculate_night:
            recommendation_full += """🌙 NACHT (bis 7:00):
   ⏰ Nicht verfügbar (Script vor 15:10 Uhr)
   Preise erst ab 15:10 Uhr verfügbar

"""
        
        if total_day > 0:
            recommendation_full += """☀️ TAG (8-20h + PV):
   Zeit: {0}-{1} Uhr
   Ladung: {2} kWh (100%)
   Kosten: {3} €
   PV-Nutzung: {4} kWh
   Ersparnis: {5} €
   🔧 go-e Max: {6} ct/kWh

""".format(start_day, end_day, round(car_capacity, 1), round(total_day_with_pv, 2), 
           round(pv_for_charging, 1), round(total_day - total_day_with_pv, 2), round(spot_day, 2))
        
        recommendation_full += "✅ BESTE OPTION\n"
        
        # Beste Option ermitteln - MIT FEHLERBEHANDLUNG
        costs = []
        if total_flex > 0:
            costs.append((total_flex, 'FLEXIBEL', spot_flex))
        if total_night > 0:
            costs.append((total_night, 'NACHT', spot_night))
        if total_day_with_pv >= 0 and total_day > 0:
            costs.append((total_day_with_pv, 'TAG MIT PV', spot_day))
        
        if costs:
            try:
                best_cost_val, best_name, best_goe = min(costs, key=lambda x: x[0])
                
                if wait_for_sun:
                    recommendation_full += "⚠️ WARTE BIS MORGEN!\n"
                    recommendation_full += "Morgen: {0} kWh Sonne verfügbar\n".format(round(pv_tomorrow_kwh, 1))
                    recommendation_full += "Potentielle PV-Ersparnis: ~{0} €\n".format(round((pv_tomorrow_kwh * 0.7 * 0.12), 2))
                else:
                    recommendation_full += "💰 {0}: {1} €\n".format(best_name, round(best_cost_val, 2))
                    recommendation_full += "🔧 go-e Charger Max Price: {0} ct/kWh\n".format(round(best_goe, 2))
                    
                    if best_name == 'TAG MIT PV' and total_day > 0:
                        recommendation_full += "✅ Spart {0}€ durch PV statt Netz!\n".format(round(total_day - total_day_with_pv, 2))
                    
                    others = [c for c in costs if c[1] != best_name]
                    if others:
                        max_other = max(others, key=lambda x: x[0])[0]
                        saving = max_other - best_cost_val
                        if saving > 0:
                            recommendation_full += "✅ Spare bis zu {0} €!".format(round(saving, 2))
            except Exception as e:
                logger.error(f"Fehler bei der Empfehlungsberechnung: {e}")
                recommendation_full += "⚠️ Fehler bei der Kostenberechnung"
        else:
            recommendation_full += "⚠️ Keine Ladeoptionen verfügbar (prüfe Spotty-Daten)"
    
    # Sensor für Empfehlung - sicherer State-Wert
    recommendation_state = state_summary if state_summary else "Keine Empfehlung verfügbar"
    recommendation_attributes = clean_attributes({
        'friendly_name': 'Ladeempfehlung',
        'full_text': recommendation_full if recommendation_full else "Keine Empfehlung",
        'short_summary': short_summary if short_summary else "Keine Zusammenfassung",
        'charging_vehicle': charging_car,
        'using_vehicle': using_car,
        'wait_for_sun': wait_for_sun,
        'pv_today': round(pv_today_kwh, 1) if pv_today_kwh else 0.0,
        'pv_tomorrow': round(pv_tomorrow_kwh, 1) if pv_tomorrow_kwh else 0.0,
        'best_scenario': 'wait_for_sun' if wait_for_sun else best_scenario,
        'flex_total': round(total_flex, 2) if total_flex and calculate_night else 0.0,
        'night_total': round(total_night, 2) if total_night and calculate_night else 0.0,
        'day_pv_total': round(total_day_with_pv, 2) if total_day_with_pv is not None else 0.0,
        'last_update': current_time,
        'night_calculation_active': calculate_night
    })
    hass.states.set('sensor.ev_optimizer_recommendation', recommendation_state, recommendation_attributes)
    
    logger.info("✅ E-Auto Optimierung erfolgreich durchgeführt")
    logger.info(f"Short Summary erstellt: {len(short_summary)} Zeichen")
    
    # WICHTIG: Python Scripts müssen ein Dictionary zurückgeben!
    data = {}

except Exception as e:
    logger.error(f"❌ FEHLER im E-Auto Optimizer: {e}")
    # WICHTIG: traceback ist in Python Scripts NICHT erlaubt!
    
    error_attributes = clean_attributes({
        'friendly_name': 'Ladeempfehlung',
        'short_summary': f"❌ Fehler: {str(e)}",
        'error': str(e),
        'error_type': str(type(e))  # GEÄNDERT: __name__ ist nicht erlaubt!
    })
    hass.states.set('sensor.ev_optimizer_recommendation', "Fehler bei Berechnung", error_attributes)
    
    # WICHTIG: Auch im Error-Fall muss data zurückgegeben werden!
    data = {}
