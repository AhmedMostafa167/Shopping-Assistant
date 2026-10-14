"""Demo storefront: a phone-accessories shop with the Shopping Assistant as its chat.

The page is a plain HTTP client of the API, as a real store's website would be. Start the
API first, then:

    uv run --group demo python demo/app.py
"""
import html
import os

import gradio as gr
import httpx

API_URL = os.getenv("SHOPPING_API_URL", "http://localhost:8001/api/v1")
STORE_NAME = "Volt Mobile"
# Demo shoppers; each one's preferences are remembered across conversations.
CUSTOMERS = {"Sara": "sara-demo", "Omar": "omar-demo"}
# The API's limit; longer messages are rejected with 422.
MAX_MESSAGE_CHARACTERS = 2000
EXAMPLES = [
    "I always prefer black accessories. Find me a phone stand.",
    "I need a phone case under $15.",
    "I only buy Samsung products. Show me a fast charger.",
]

client = httpx.Client(base_url=API_URL, timeout=120)

CSS = """
.store-header {background: linear-gradient(120deg, #1e1b4b, #4338ca); color: #fff;
  border-radius: 14px; padding: 18px 24px;}
.store-header h1 {margin: 0; font-size: 1.7rem; color: #fff;}
.store-header p {margin: 4px 0 0; opacity: .85;}
.store-nav {margin-top: 10px; display: flex; gap: 18px; font-size: .9rem; opacity: .9;}
.cards {display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px;}
.card {border: 1px solid var(--border-color-primary); border-radius: 12px; padding: 10px;
  background: var(--background-fill-primary); display: flex; flex-direction: column; gap: 6px;}
.card img {width: 100%; height: 140px; object-fit: contain; background: #fff; border-radius: 8px;}
.card .title {font-size: .82rem; line-height: 1.25; display: -webkit-box; -webkit-line-clamp: 3;
  -webkit-box-orient: vertical; overflow: hidden;}
.card .price {font-weight: 700; font-size: 1rem;}
.card .price.missing {font-weight: 400; font-size: .85rem; opacity: .7;}
.card .score {font-size: .75rem; opacity: .75;}
.facts {display: flex; flex-direction: column; gap: 6px;}
.fact {border-left: 3px solid #4338ca; padding: 4px 8px; font-size: .88rem;}
.fact .type {font-size: .7rem; text-transform: uppercase; letter-spacing: .04em; opacity: .65;}
.empty {opacity: .65; font-size: .88rem;}
"""

HEADER = f"""
<div class="store-header">
  <h1>⚡ {STORE_NAME}</h1>
  <p>Phones and accessories. Ask our shopping assistant in your own words; it remembers what you like.</p>
  <div class="store-nav"><span>Cases</span><span>Chargers</span><span>Stands &amp; mounts</span>
  <span>Cables</span><span>Audio</span></div>
</div>
"""


def product_cards_html(products: list[dict]) -> str:
    if not products:
        return '<p class="empty">Products the assistant finds will appear here.</p>'
    cards = []
    for product in products:
        if product.get("price") is None:
            price = '<div class="price missing">Price not listed</div>'
        else:
            price = f'<div class="price">${product["price"]:,.2f}</div>'
        score = product.get("recommendation_score")
        score_html = f'<div class="score">Recommendation score {score:.2f}/5</div>' if score is not None else ""
        image = html.escape(product.get("image") or "", quote=True)
        image_html = f'<img src="{image}" alt="" loading="lazy" referrerpolicy="no-referrer">' if image else ""
        cards.append(
            f'<div class="card">{image_html}<div class="title">{html.escape(product["title"])}</div>'
            f"{price}{score_html}</div>"
        )
    return f'<div class="cards">{"".join(cards)}</div>'


def memory_html(username: str) -> str:
    try:
        response = client.get(f"/profiles/{username}/memories")
        response.raise_for_status()
        facts = response.json()
    except httpx.HTTPError:
        return '<p class="empty">Could not load stored preferences.</p>'
    if not facts:
        return '<p class="empty">Nothing yet. Tell the assistant about your phone, budget or style.</p>'
    items = "".join(
        f'<div class="fact"><div class="type">{html.escape(fact["fact_type"])}</div>'
        f'{html.escape(fact["content"])}</div>'
        for fact in facts
    )
    return f'<div class="facts">{items}</div>'


def message_text(content) -> str:
    """Gradio returns a message's content as a list of parts; keep the text."""
    if isinstance(content, str):
        return content
    return " ".join(part.get("text", "") for part in content if isinstance(part, dict)).strip()


def fresh_session() -> dict:
    return {"conversation_id": None, "trace_ids": {}}


def add_user_message(message: str, history: list):
    message = message.strip()
    if not message:
        return "", history
    return "", history + [{"role": "user", "content": message}]


def answer(history: list, customer: str, session: dict):
    if not history or history[-1]["role"] != "user":
        return history, session, gr.update(), gr.update()
    username = CUSTOMERS[customer]
    products = []
    try:
        if session["conversation_id"] is None:
            created = client.post("/conversations", json={"username": username, "title": "Storefront chat"})
            created.raise_for_status()
            session["conversation_id"] = created.json()["conversation_id"]
        text = message_text(history[-1]["content"])
        response = client.post("/chat", json={
            "username": username,
            "conversation_id": session["conversation_id"],
            "message": text,
        })
        if response.status_code == 422 and len(text) > MAX_MESSAGE_CHARACTERS:
            reply = f"That message is too long. Please keep it under {MAX_MESSAGE_CHARACTERS:,} characters."
        else:
            response.raise_for_status()
            data = response.json()
            reply, products = data["response"], data["products"]
            if data.get("trace_id"):
                session["trace_ids"][len(history)] = data["trace_id"]
    except httpx.HTTPError as error:
        reply = f"Sorry, the assistant is unavailable right now ({error.__class__.__name__})."
    history = history + [{"role": "assistant", "content": reply}]
    return history, session, product_cards_html(products), memory_html(username)


def rate_reply(feedback: gr.LikeData, customer: str, session: dict):
    index = feedback.index[0] if isinstance(feedback.index, (list, tuple)) else feedback.index
    trace_id = session["trace_ids"].get(index)
    if trace_id is None:
        return
    response = client.post("/chat/feedback", json={
        "username": CUSTOMERS[customer],
        "conversation_id": session["conversation_id"],
        "trace_id": trace_id,
        "helpful": feedback.liked in (True, "like"),
    })
    if response.is_success:
        gr.Info("Thanks for your feedback!")


def switch_customer(customer: str):
    return [], fresh_session(), product_cards_html([]), memory_html(CUSTOMERS[customer])


with gr.Blocks(title=f"{STORE_NAME}: shopping assistant") as demo:
    session = gr.State(fresh_session())
    gr.HTML(HEADER)
    with gr.Row():
        with gr.Column(scale=3):
            chatbot = gr.Chatbot(
                height=520,
                label="Shopping assistant",
                feedback_options=("Like", "Dislike"),
                placeholder="Hi! What are you shopping for today?",
            )
            message = gr.Textbox(placeholder="Ask about a product, your budget, or your phone…",
                                 show_label=False, submit_btn=True)
            with gr.Row():
                example_buttons = [gr.Button(text, size="sm", variant="secondary") for text in EXAMPLES]
        with gr.Column(scale=2):
            with gr.Row():
                customer = gr.Radio(list(CUSTOMERS), value="Sara", label="Signed in as")
                new_chat = gr.Button("New conversation", size="sm")
            gr.Markdown("### Products")
            products_panel = gr.HTML(product_cards_html([]))
            gr.Markdown("### What I remember about you")
            memory_panel = gr.HTML()
    gr.Markdown(
        "<small>Demo store. Products, prices and images come from the catalogue database; "
        "replies come from the Shopping Assistant agent, and every reply is traced in Langfuse.</small>"
    )

    reply_outputs = [chatbot, session, products_panel, memory_panel]
    message.submit(add_user_message, [message, chatbot], [message, chatbot]).then(
        answer, [chatbot, customer, session], reply_outputs)
    for button in example_buttons:
        button.click(lambda text=button.value: text, None, message).then(
            add_user_message, [message, chatbot], [message, chatbot]).then(
            answer, [chatbot, customer, session], reply_outputs)
    chatbot.like(rate_reply, [customer, session], None)
    customer.change(switch_customer, customer, [chatbot, session, products_panel, memory_panel])
    new_chat.click(switch_customer, customer, [chatbot, session, products_panel, memory_panel])
    demo.load(lambda c: memory_html(CUSTOMERS[c]), customer, memory_panel)


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("DEMO_PORT", "7860")),
        theme=gr.themes.Soft(primary_hue="indigo"),
        css=CSS,
    )
