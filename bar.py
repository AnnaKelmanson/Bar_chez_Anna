"""A tiny home bar menu and shopping calculator. Python standard library only."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def available_ingredients(inventory):
    return {item["type"].casefold() for category in ("bottles", "syrups", "always_available")
            for item in inventory[category] if item["at_home"]}


def options(recipes):
    for name, recipe in recipes.items():
        if recipe.get("variations"):
            for variant, details in recipe["variations"].items():
                yield f"{name} / {variant}", dict(
                    recipe, ingredients=recipe["ingredients"] + details.get("additional_ingredients", []))
        else:
            yield name, recipe


def availability(recipe, available):
    unresolved = not recipe["ingredients"]
    missing = []
    for ingredient, _, _ in recipe["ingredients"]:
        if "to confirm" in ingredient:
            unresolved = True
        elif ingredient.casefold() not in available:
            missing.append(ingredient)
    return sorted(set(missing)), unresolved


def item_label(item):
    return item["type"] + (f" ({item['brand']})" if item["brand"] else "")


def linked(name, url):
    return f"[{name}]({url})" if name and url else str(url or name)


def ingredient_text(row):
    name, amount, unit = row
    if unit == "by eye" or amount is None:
        return name
    if unit.casefold() in name.casefold():
        return f"{amount:g} {name}"
    return f"{amount:g} {unit} {name}"


def recipe_line(recipe):
    parts = [ingredient_text(row) for row in recipe["ingredients"]]
    if recipe.get("garnish"):
        parts.append(recipe["garnish"])
    return ", ".join(parts)


def markdown_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return lines


def wishlist_items(inventory, extras):
    bottle_urls = {item.get("purchase_url") for item in inventory["bottles"] if item.get("purchase_url")}
    bottle_names = {name.casefold() for item in inventory["bottles"] for name in (item["type"], item_label(item))}
    items = [{"name": item_label(item), "url": item.get("purchase_url")}
             for item in inventory["bottles"] if item["at_home"] is False]
    items += [gift for gift in extras
              if gift.get("url") not in bottle_urls and (gift.get("name") or "").casefold() not in bottle_names]
    return items


def missing_rows(recipes, inventory, available):
    urls = {item["type"].casefold(): item.get("purchase_url")
            for category in ("bottles", "syrups", "always_available") for item in inventory[category]}
    rows = []
    for name, recipe in options(recipes):
        missing, unresolved = availability(recipe, available)
        if missing and not unresolved:
            rows.append((name, ", ".join(linked(item, urls.get(item.casefold())) for item in missing)))
    return rows or [("Nothing, everything is available.", "")]


def readme_text(recipes, inventory, wishlist):
    available = available_ingredients(inventory)
    makeable = [(name, recipe_line(recipe)) for name, recipe in options(recipes)
                if not any(availability(recipe, available))] or [("Nothing yet.", "")]
    missing_alcohol = [(linked(gift.get("name"), gift.get("url")),) for gift in wishlist] or [("Nothing yet.",)]
    lines = [
        "# Bar chez Anna",
        "",
        "Hi! I'm Anna and I love making cocktails, and you love drinking them.",
        "",
        "Come over to my home bar for a cocktail night.",
        "",
        "This repo shows what I can make at home right now:",
        "",
        "## Available menu",
        "",
    ]
    lines.extend(markdown_table(("Cocktail", "Build"), makeable))
    lines.extend([
        "",
        "## Not available yet",
        "",
        "I have more recipes, but I don't have everything at home to make them yet. "
        "If you want one of these, bring the missing ingredients and I'll make it for you.",
        "",
        "I usually have the basics at home (ice, lemons, eggs), but check with me before you come "
        "in case you should bring some.",
        "",
    ])
    lines.extend(markdown_table(("Cocktail", "Bring"), missing_rows(recipes, inventory, available)))
    lines.extend([
        "",
        "If you like what I do, you can contribute by buying something from the wishlist. If you don't know what to get me for my birthday or Christmas, pick something from that list.",
        "",
        "## Wishlist",
        "",
    ])
    lines.extend(markdown_table(("Item",), missing_alcohol))
    return "\n".join(lines) + "\n"


def write_readme(recipes, inventory):
    wishlist_path = ROOT / "wishlist.json"
    extras = json.loads(wishlist_path.read_text(encoding="utf-8")) if wishlist_path.exists() else []
    wishlist = wishlist_items(inventory, extras)
    wishlist_path.write_text(json.dumps(wishlist, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    text = readme_text(recipes, inventory, wishlist)
    (ROOT / "README.md").write_text(text, encoding="utf-8")
    return text


def requirements(orders, recipes):
    totals = defaultdict(float)
    for name, count in orders:
        recipe = recipes[name]
        if not recipe["ingredients"] or any(
            amount is None and unit != "by eye" for _, amount, unit in recipe["ingredients"]
        ):
            raise ValueError(f"{name} is a draft. Confirm its recipe before calculating quantities.")
        for ingredient, amount, unit in recipes[name]["ingredients"]:
            if unit == "by eye":
                continue
            totals[ingredient, unit] += amount * count
    return totals


def main():
    parser = argparse.ArgumentParser(description="Your home bar recipes and party quantities")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("menu", help="List cocktails and any missing ingredients")
    stock = commands.add_parser("stock", help="Посмотреть или изменить запасы")
    stock.add_argument("action", choices=("list", "add", "remove"), nargs="?", default="list")
    stock.add_argument("items", nargs="*")
    stock.add_argument("--category", choices=("bottles", "syrups", "always_available"), default="bottles")
    shopping = commands.add_parser("shopping", help="Что докупить для коктейля")
    shopping.add_argument("names", nargs="+")
    commands.add_parser("readme", help="Перезаписать README.md из текущих запасов и рецептов")
    recipe = commands.add_parser("recipe", help="Show one recipe")
    recipe.add_argument("name")
    plan = commands.add_parser("plan", help='Total quantities, e.g. "Cocktail name=4"')
    plan.add_argument("orders", nargs="+")
    args = parser.parse_args()
    recipes = read("recipes.json")
    inventory = read("bottles.json")
    available = available_ingredients(inventory)
    if args.command == "stock":
        if args.action != "list":
            if not args.items or any(not item.strip() for item in args.items):
                parser.error("Укажи ингредиенты в кавычках.")
            for item in args.items:
                item = item.strip()
                for category in ("bottles", "syrups", "always_available"):
                    inventory[category] = [value for value in inventory[category]
                                           if value["type"].casefold() != item.casefold()]
                if args.action == "add":
                    inventory[args.category].append(
                        {"type": item, "brand": None, "purchase_url": None, "at_home": True})
            (ROOT / "bottles.json").write_text(
                json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print("Запасы обновлены.")
            write_readme(recipes, inventory)
        for category, title in (("bottles", "Алкоголь дома"), ("syrups", "Сиропы дома"),
                                ("always_available", "Считаем всегда доступным")):
            print(title + ": " + ", ".join(
                item["type"] + (f" ({item['brand']})" if item["brand"] else "")
                + ("" if item["at_home"] is True else " [нет дома]" if item["at_home"] is False else " [не проверено]")
                for item in inventory[category]))
        return
    if args.command == "readme":
        print(write_readme(recipes, inventory), end="")
        return
    if args.command == "shopping":
        choices = dict(options(recipes))
        unknown = [name for name in args.names if name not in choices]
        if unknown:
            parser.error("Неизвестный коктейль или вариант: " + ", ".join(unknown))
        combined = set()
        for name in args.names:
            missing, unresolved = availability(choices[name], available)
            combined.update(missing)
            print(name + ": " + ("докупить " + ", ".join(missing) if missing else "все записанные ингредиенты есть"))
            if unresolved:
                print("  Состав не уточнён полностью; список покупок может быть неполным.")
        print("Общий список покупок: " + (", ".join(sorted(combined)) or "пусто"))
        return
    if not recipes:
        print("No cocktails yet. Add your own recipes to recipes.json to get started.")
        return
    if args.command == "menu":
        groups = {"Можно приготовить по наличию ингредиентов": [], "Нужно докупить": [], "Нужно уточнить состав": []}
        for name, recipe in options(recipes):
            missing, unresolved = availability(recipe, available)
            if unresolved:
                groups["Нужно уточнить состав"].append(name + (": не хватает " + ", ".join(missing) if missing else ""))
            elif missing:
                groups["Нужно докупить"].append(name + ": " + ", ".join(missing))
            else:
                groups["Можно приготовить по наличию ингредиентов"].append(name)
        for title, entries in groups.items():
            print(title + ":")
            for entry in entries:
                print("  " + entry)
            if not entries:
                print("  —")
    elif args.command == "recipe":
        if args.name not in recipes:
            parser.error(f"Unknown cocktail: {args.name}. Run menu to see names.")
        recipe = recipes[args.name]
        print(args.name)
        for ingredient, amount, unit in recipe["ingredients"]:
            if unit == "by eye":
                print(f"  {ingredient}: by eye")
                continue
            quantity = f"{amount:g}" if amount is not None else "TBC"
            print(f"  {quantity} {unit} {ingredient}")
        for name, variation in recipe.get("variations", {}).items():
            print("Variant: " + name)
            for row in variation.get("additional_ingredients", []):
                print("  + " + ingredient_text(row))
        if recipe.get("garnish"):
            print("Garnish: " + recipe["garnish"])
        if recipe.get("source"):
            print("Source: " + recipe["source"])
    else:
        orders = []
        for order in args.orders:
            try:
                name, raw_count = order.rsplit("=", 1)
                count = int(raw_count)
            except ValueError:
                parser.error(f'Invalid order: {order}. Use "Cocktail=positive_integer".')
            if name not in recipes or count <= 0:
                parser.error(f"Unknown cocktail or nonpositive count: {order}")
            orders.append((name, count))
        try:
            totals = requirements(orders, recipes)
        except ValueError as error:
            parser.error(str(error))
        print(f"Ingredients for {sum(count for _, count in orders)} drinks:")
        for (ingredient, unit), amount in sorted(totals.items()):
            status = "" if ingredient.casefold() in available else " [not in your bar]"
            print(f"  {amount:g} {unit} {ingredient}{status}")
        unmeasured = sorted({ingredient for name, _ in orders
                             for ingredient, _, unit in recipes[name]["ingredients"]
                             if unit == "by eye"})
        for ingredient in unmeasured:
            print(f"  {ingredient}: by eye (not included in measured totals)")
        print("Totals are required quantities, not purchases: bottle amounts are not tracked.")
        print("Allow extra ice and garnishes; these are not included in the totals.")


def _check_wishlist():
    inventory = {"bottles": [
        {"type": "Gin", "brand": "A", "purchase_url": "http://gin", "at_home": False},
        {"type": "Rum", "brand": None, "purchase_url": "http://rum", "at_home": True},
    ]}
    extras = [{"name": "Gin (A)", "url": "http://gin"}, {"name": "Glass", "url": "http://glass"}]
    assert wishlist_items(inventory, extras) == [
        {"name": "Gin (A)", "url": "http://gin"},
        {"name": "Glass", "url": "http://glass"},
    ]


if __name__ == "__main__":
    _check_wishlist()
    main()
