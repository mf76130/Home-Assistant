"""
Home Assistant python_script:
Strompreis-HOCHPREIS-PHASEN für das NEUESTE Datum im Sensor
OHNE IMPORTS - findet automatisch das späteste verfügbare Datum
"""

# --- Konfiguration ---
SCHWELLWERT_METHODE = 'percentile'
PERCENTILE_WERT = 70
MIN_PHASE_DAUER = 120
MAX_GAP_DAUER = 90
sensor_entity = 'sensor.spotty_15_future'

# --- Hilfsfunktionen ---
def percentile(data, p):
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 0:
        return None
    k = (n - 1) * p / 100.0
    f = int(k)
    c = f + 1
    if c >= n:
        return sorted_data[-1]
    d0 = sorted_data[f]
    d1 = sorted_data[c]
    return d0 + (d1 - d0) * (k - f)

def fmt_two(n):
    return str(n).zfill(2)

def build_iso_from_parts(y, mo, d, hour, minute, second, tz):
    date_str = '{}-{}-{}'.format(str(y).zfill(4), fmt_two(mo), fmt_two(d))
    time_str = '{}:{}:{}'.format(fmt_two(hour), fmt_two(minute), fmt_two(second))
    return date_str + 'T' + time_str + (tz if tz else '')

def add_minutes_to_iso(iso, minutes_delta):
    if not iso or 'T' not in iso:
        return None, None
    date_part, time_part = iso.split('T', 1)
    try:
        y, mo, d = date_part.split('-')
        year = int(y); month = int(mo); day = int(d)
    except Exception:
        return None, None
    tz = ''
    time_core = time_part
    if time_part.endswith('Z'):
        tz = 'Z'
        time_core = time_part[:-1]
    else:
        plus = time_part.find('+')
        minus = time_part.find('-', 2)
        if plus != -1:
            tz = time_part[plus:]
            time_core = time_part[:plus]
        elif minus != -1:
            tz = time_part[minus:]
            time_core = time_part[:minus]
    parts = time_core.split(':')
    try:
        hour = int(parts[0]) if len(parts) >= 1 and parts[0] != '' else 0
        minute = int(parts[1]) if len(parts) >= 2 and parts[1] != '' else 0
        second = 0
    except Exception:
        return None, None
    
    total = hour * 60 + minute + minutes_delta
    days_delta, rem = divmod(total, 1440)
    new_h = rem // 60
    new_m = rem % 60
    
    def is_leap_year(y):
        return (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0))
    
    def days_in_month(y, m):
        if m == 2:
            return 29 if is_leap_year(y) else 28
        if m in (1,3,5,7,8,10,12):
            return 31
        return 30
    
    d2 = day + days_delta
    m2 = month
    y2 = year
    while d2 < 1:
        m2 -= 1
        if m2 < 1:
            m2 = 12
            y2 -= 1
        d2 += days_in_month(y2, m2)
    while True:
        dim = days_in_month(y2, m2)
        if d2 <= dim:
            break
        d2 -= dim
        m2 += 1
        if m2 > 12:
            m2 = 1
            y2 += 1
    
    new_iso = build_iso_from_parts(y2, m2, d2, new_h, new_m, 0, tz)
    new_hm = '{}:{}'.format(fmt_two(new_h), fmt_two(new_m))
    return new_iso, new_hm

# --- Hauptlogik ---
sensor_state = hass.states.get(sensor_entity)

if not sensor_state:
    logger.error("Sensor nicht gefunden")
    hass.states.set('sensor.strompreis_berge_alle', 'error', {'error': 'Sensor nicht gefunden'})
else:
    sensor_data = sensor_state.attributes.get('data', [])
    if not sensor_data:
        hass.states.set('sensor.strompreis_berge_alle', 0, {'berge': [], 'error': 'Keine Daten'})
    else:
        daten_pro_tag = {}
        for slot in sensor_data:
            try:
                slot_time_str = slot.get('start_time')
                if not slot_time_str or 'T' not in slot_time_str:
                    continue
                datum = slot_time_str.split('T')[0]
                zeit_teil = slot_time_str.split('T')[1]
                uhrzeit = zeit_teil.split(':')[0] + ':' + zeit_teil.split(':')[1]
                if datum not in daten_pro_tag:
                    daten_pro_tag[datum] = []
                daten_pro_tag[datum].append({
                    'time_str': slot_time_str,
                    'uhrzeit': uhrzeit,
                    'price': float(slot.get('price_per_kwh', 0))
                })
            except Exception:
                continue
        
        verfuegbare_daten = sorted(daten_pro_tag.keys())
        if len(verfuegbare_daten) == 0:
            hass.states.set('sensor.strompreis_berge_alle', 0, {'berge': [], 'error': 'Keine Daten'})
        else:
            ziel_datum = verfuegbare_daten[-1]
            logger.info("Verwende NEUSTES Datum: %s" % ziel_datum)
            
            ziel_daten = daten_pro_tag[ziel_datum]
            ziel_daten.sort(key=lambda x: x['time_str'])
            n = len(ziel_daten)
            
            if n < 10:
                hass.states.set('sensor.strompreis_berge_alle', 0, {'berge': [], 'error': 'Zu wenige Slots', 'datum': ziel_datum})
            else:
                preise = [d['price'] for d in ziel_daten]
                schwellwert = percentile(preise, PERCENTILE_WERT)
                
                logger.info("Schwellwert: %.2f ct/kWh" % schwellwert)
                
                hochpreis_segmente = []
                in_segment = False
                segment_start = -1
                
                for i in range(n):
                    if ziel_daten[i]['price'] >= schwellwert:
                        if not in_segment:
                            in_segment = True
                            segment_start = i
                    else:
                        if in_segment:
                            hochpreis_segmente.append((segment_start, i - 1))
                            in_segment = False
                
                if in_segment:
                    hochpreis_segmente.append((segment_start, n - 1))
                
                if len(hochpreis_segmente) == 0:
                    finale_phasen = []
                else:
                    finale_phasen = [list(hochpreis_segmente[0])]
                    for i in range(1, len(hochpreis_segmente)):
                        letzte_phase_ende = finale_phasen[-1][1]
                        aktuelle_phase_start = hochpreis_segmente[i][0]
                        gap_minuten = (aktuelle_phase_start - letzte_phase_ende - 1) * 15
                        if gap_minuten <= MAX_GAP_DAUER:
                            finale_phasen[-1][1] = hochpreis_segmente[i][1]
                        else:
                            finale_phasen.append(list(hochpreis_segmente[i]))
                
                lange_phasen = []
                for start_idx, end_idx in finale_phasen:
                    if (end_idx - start_idx + 1) * 15 >= MIN_PHASE_DAUER:
                        lange_phasen.append((start_idx, end_idx))
                
                berge = []
                for phase_nr, (start_idx, end_idx) in enumerate(lange_phasen, 1):
                    phase_preise = [ziel_daten[i]['price'] for i in range(start_idx, end_idx + 1)]
                    max_preis = max(phase_preise)
                    peak_idx = start_idx + phase_preise.index(max_preis)
                    
                    start_iso_original = ziel_daten[start_idx]['time_str']
                    final_start_iso, final_start_hm = add_minutes_to_iso(start_iso_original, -30)
                    if not final_start_iso:
                        final_start_iso = start_iso_original
                        final_start_hm = ziel_daten[start_idx]['uhrzeit']
                    
                    end_iso_original = ziel_daten[end_idx]['time_str']
                    final_end_iso, final_end_hm = add_minutes_to_iso(end_iso_original, 30)
                    if not final_end_iso:
                        final_end_iso = end_iso_original
                        final_end_hm = ziel_daten[end_idx]['uhrzeit']
                    
                    berge.append({
                        'datum': ziel_datum,
                        'phase_nr': phase_nr,
                        'anstieg_start': final_start_hm,
                        'anstieg_start_iso': final_start_iso,
                        'peak_zeit': ziel_daten[peak_idx]['uhrzeit'],
                        'peak_preis': round(max_preis, 2),
                        'abstieg_ende': final_end_hm,
                        'abstieg_ende_iso': final_end_iso,
                        'gesamt_dauer': (end_idx - start_idx + 1) * 15
                    })
                
                hass.states.set('sensor.strompreis_berge_alle', len(berge), {
                    'berge': berge,
                    'anzahl': len(berge),
                    'datum': ziel_datum,
                    'verfuegbare_daten': verfuegbare_daten,
                    'schwellwert_berechnet': round(schwellwert, 2),
                    'unit_of_measurement': 'Berge'
                })
                
                logger.info("FERTIG: %d Phasen für %s" % (len(berge), ziel_datum))
