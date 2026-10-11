from agent.tools import format_price, format_recommendation_score
from models.db_schemes import Product


def score(average_rating, rating_number):
    return Product(
        average_rating=average_rating, rating_number=rating_number
    ).recommendation_score


def test_products_without_usable_rating_have_no_score():
    assert score(None, None) is None
    assert score(4.5, 0) is None
    assert score(float("nan"), 120) is None


def test_tool_output_says_when_a_product_has_no_ratings():
    assert format_recommendation_score(Product()) == "no ratings yet"


def test_tool_output_labels_the_score_as_not_the_average_rating():
    rated = Product(average_rating=4.5, rating_number=200)

    text = format_recommendation_score(rated)

    assert text.startswith(f"recommendation score {rated.recommendation_score}/5")
    assert "not the average rating" in text


def test_tool_output_never_shows_a_missing_price_as_a_number():
    assert format_price(Product(price=19.99)) == "$19.99"
    assert format_price(Product(price=None)) == "price not listed"
    assert format_price(Product(price=float("nan"))) == "price not listed"



def test_more_ratings_raise_the_score_for_the_same_average():
    assert score(4.5, 5) < score(4.5, 50) < score(4.5, 5000)


def test_score_stays_on_the_rating_scale_and_below_the_average():
    for average, count in [(1.0, 3), (3.2, 40), (5.0, 2), (5.0, 10000)]:
        assert 1.0 <= score(average, count) <= average


def test_many_good_ratings_beat_a_few_perfect_ones():
    assert score(4.6, 2000) > score(5.0, 3)
