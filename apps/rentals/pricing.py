"""Internal rent estimates based on an owner's existing room prices."""

from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError

from .models import Room


def suggest_room_price(room: Room):
    try:
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
        from sklearn.model_selection import train_test_split
    except ImportError as exc:
        raise ValidationError("Chưa cài scikit-learn. Chạy pip install -r requirements.txt.") from exc

    if room.area is None or room.area <= 0:
        raise ValidationError("Cần nhập diện tích phòng trước khi gợi ý giá.")

    peers = list(
        Room.objects.filter(building__owner_id=room.building.owner_id, area__gt=0, monthly_rent__gt=0)
        .exclude(pk=room.pk)
        .select_related("building")
        .prefetch_related("amenities")
    )
    if len(peers) < 8:
        raise ValidationError("Cần ít nhất 8 phòng khác của cùng chủ nhà có diện tích và giá thuê để tạo gợi ý.")

    building_ids = sorted({str(item.building_id) for item in peers} | {str(room.building_id)})
    amenity_ids = sorted({str(a.id) for item in peers + [room] for a in item.amenities.all()})

    def features(item):
        item_amenities = {str(a.id) for a in item.amenities.all()}
        return [
            float(item.area),
            int(item.floor),
            int(item.max_occupants),
            *[int(str(item.building_id) == key) for key in building_ids],
            *[int(key in item_amenities) for key in amenity_ids],
        ]

    x = [features(item) for item in peers]
    y = [float(item.monthly_rent) for item in peers]
    validation_mae = None
    validation_rmse = None
    validation_r2 = None
    if len(peers) >= 20:
        train_x, test_x, train_y, test_y = train_test_split(x, y, test_size=0.2, random_state=42)
        validation_model = RandomForestRegressor(n_estimators=120, min_samples_leaf=2, random_state=42, n_jobs=1)
        validation_model.fit(train_x, train_y)
        test_predictions = validation_model.predict(test_x)
        validation_mae = Decimal(str(mean_absolute_error(test_y, test_predictions)))
        validation_rmse = Decimal(str(mean_squared_error(test_y, test_predictions) ** 0.5))
        validation_r2 = Decimal(str(r2_score(test_y, test_predictions)))

    model = RandomForestRegressor(n_estimators=120, min_samples_leaf=2, random_state=42, n_jobs=1)
    model.fit(x, y)
    predicted = max(0, float(model.predict([features(room)])[0]))
    suggested = (Decimal(str(predicted)) / Decimal("10000")).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * Decimal("10000")
    snapshot = {
        "area": str(room.area),
        "floor": room.floor,
        "max_occupants": room.max_occupants,
        "building_id": str(room.building_id),
        "amenity_ids": sorted(str(a.id) for a in room.amenities.all()),
        "method": "RandomForestRegressor",
        "source": "giá niêm yết của các phòng cùng chủ nhà",
    }
    return suggested, len(peers), validation_mae, validation_rmse, validation_r2, snapshot
