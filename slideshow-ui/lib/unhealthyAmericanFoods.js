/** Large pool of unhealthy / ultra-processed American grocery & fast-food items. */

export const UNHEALTHY_AMERICAN_FOOD_CATEGORIES = [
  {
    name: "Sugary drinks",
    items: [
      "Coca-Cola", "Pepsi", "Mountain Dew", "Dr Pepper", "Sprite", "Fanta Orange",
      "Red Bull", "Monster Energy", "Gatorade", "Powerade", "Arizona Iced Tea",
      "Starbucks Frappuccino bottle", "Capri Sun", "SunnyD", "Welch's grape soda",
    ],
  },
  {
    name: "Chips & salty snacks",
    items: [
      "Doritos Nacho Cheese", "Cheetos", "Lay's Classic", "Ruffles", "Fritos",
      "Takis Fuego", "Pringles Original", "Cheetos Flamin Hot", "Funyuns",
      "Goldfish crackers", "Combos", "Bugles", "Chex Mix", "Pretzel Crisps",
    ],
  },
  {
    name: "Candy & cookies",
    items: [
      "Oreos", "Chips Ahoy", "Nutter Butter", "Little Debbie Swiss Rolls",
      "Snickers", "Reese's Peanut Butter Cups", "M&M's", "Skittles", "Twix",
      "Kit Kat", "Sour Patch Kids", "Hostess Twinkies", "Pop-Tarts Brown Sugar",
    ],
  },
  {
    name: "Fast food",
    items: [
      "McDonald's Big Mac", "Burger King Whopper", "Wendy's Baconator",
      "Taco Bell Crunchwrap Supreme", "KFC Original Recipe bucket",
      "Popeyes chicken sandwich", "Chick-fil-A nuggets", "Five Guys cheeseburger",
      "Domino's pepperoni pizza", "Pizza Hut stuffed crust", "Subway footlong Italian BMT",
    ],
  },
  {
    name: "Frozen junk",
    items: [
      "Hot Pockets pepperoni", "Totino's Pizza Rolls", "Banquet chicken nuggets",
      "Hungry-Man salisbury steak", "Stouffer's mac and cheese", "Marie Callender's pot pie",
      "DiGiorno pepperoni pizza", "Bagel Bites", "Jimmy Dean breakfast sandwich",
      "Eggo waffles", "Ben & Jerry's ice cream pint",
    ],
  },
  {
    name: "Sugary cereal & breakfast",
    items: [
      "Frosted Flakes", "Froot Loops", "Lucky Charms", "Cinnamon Toast Crunch",
      "Cap'n Crunch", "Honey Buns", "Toaster Strudel", "Pop-Tarts Frosted Strawberry",
      "Honey Nut Cheerios", "Cocoa Puffs", "Frosted Mini-Wheats", "Pancake syrup bottle",
    ],
  },
  {
    name: "Instant & packaged meals",
    items: [
      "Ramen Nissin Cup Noodles", "Maruchan instant lunch", "Kraft Mac and Cheese",
      "Chef Boyardee ravioli", "Campbell's condensed soup", "Hormel chili",
      "Spam classic", "Rice-A-Roni", "Hamburger Helper", "Instant mashed potatoes",
      "Microwaveable mac bowl", "Cup of Noodles chicken",
    ],
  },
  {
    name: "Processed meat & deli",
    items: [
      "Oscar Mayer bologna", "Ball Park hot dogs", "Slim Jim", "Lunchables turkey",
      "Spam lite", "Bacon bits jar", "Corn dogs frozen box", "Pepperoni stick",
      "Beef jerky Jack Link's", "Vienna sausages", "Smoked sausage Hillshire Farm",
    ],
  },
];

/** Flat deduped list of all unhealthy American foods in the pool. */
export function allUnhealthyAmericanFoods() {
  const seen = new Set();
  const out = [];
  for (const cat of UNHEALTHY_AMERICAN_FOOD_CATEGORIES) {
    for (const item of cat.items) {
      const key = String(item || "").trim().toLowerCase();
      if (!key || seen.has(key)) continue;
      seen.add(key);
      out.push(String(item).trim());
    }
  }
  return out;
}
