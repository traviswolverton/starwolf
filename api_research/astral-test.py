from astral.moon import phase, moonrise
from astral.sun import night

def dark_hours_before_moonrise(observer, date, tz):
    """Hours of astronomical dark before moon rises — key score input."""
    dark_start, dark_end = night(observer, date=date, tzinfo=tz)
    try:
        mr = moonrise(observer, date=date, tzinfo=tz)
        if mr is None or mr >= dark_end:
            return (dark_end - dark_start).seconds / 3600  # full night clean
        elif mr <= dark_start:
            return 0  # moon already up when dark starts
        else:
            return (mr - dark_start).seconds / 3600  # partial window
    except:
        return (dark_end - dark_start).seconds / 3600  # no rise = clean night

def moon_score(observer, date, tz):
    """0–100, higher = better for stargazing."""
    p = phase(date)
    illum = (1 - abs(p - 14) / 14) * 100  # 0=new, 100=full
    dark_hrs = dark_hours_before_moonrise(observer, date, tz)
    moon_penalty = (illum / 100) * (1 - dark_hrs / 9)  # 9h ≈ max dark window
    return round((1 - moon_penalty) * 100)