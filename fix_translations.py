import json
import os

correct_translations = {
  "Hello everyone.": "سلام به همگی.",
  "Today I want to talk about my favorite TV show.": "امروز می‌خواهم درباره برنامه تلویزیونی مورد علاقه‌ام صحبت کنم.",
  "It is called Lost.": "نام آن لاست است.",
  "This American show started in 2004 and ended in 2010.": "این سریال آمریکایی در سال ۲۰۰۴ شروع شد و در سال ۲۰۱۰ به پایان رسید.",
  "It was made by J.J. Abrams and Damon Lindelof.": "این سریال توسط جی. جی. آبرامز و دیمون لیندلوف ساخته شده است.",
  "The story begins with a plane crash.": "داستان با یک سانحه سقوط هواپیما آغاز می‌شود.",
  "Flight 815 was going from Australia to the United States.": "پرواز ۸۱۵ از استرالیا به سمت ایالات متحده می‌رفت.",
  "During the flight, the plane broke into pieces and fell on a strange island.": "در حین پرواز، هواپیما تکه‌تکه شد و در جزیره‌ای عجیب سقوط کرد.",
  "About 48 people survived the crash.": "حدود ۴۸ نفر از این سانحه جان سالم به در بردند.",
  "The island is not a normal place.": "این جزیره یک مکان عادی نیست.",
  "The survivors find strange things.": "بازماندگان چیزهای عجیبی پیدا می‌کنند.",
  "There are polar bears in the jungle.": "در جنگل خرس‌های قطبی وجود دارند.",
  "There is a monster in the forest that no one can see clearly.": "هیولایی در جنگل وجود دارد که هیچ‌کس نمی‌تواند آن را به وضوح ببیند.",
  "There are also people who already live on the island.": "همچنین افرادی هستند که از قبل در جزیره زندگی می‌کنند.",
  "They are called \"The Others.\"": "آنها «دیگران» نامیده می‌شوند.",
  "The main characters are very interesting.": "شخصیت‌های اصلی بسیار جالب هستند.",
  "Jack is a doctor.": "جک یک دکتر است.",
  "He becomes the leader of the group.": "او رهبر گروه می‌شود.",
  "He is responsible but sometimes too serious.": "او مسئولیت‌پذیر است اما گاهی خیلی جدی می‌شود.",
  "Locke is a man who could not walk before the crash.": "لاک مردی است که قبل از سقوط نمی‌توانست راه برود.",
  "On the island, he can walk again.": "در جزیره، او می‌تواند دوباره راه برود.",
  "He believes the island is special.": "او معتقد است که این جزیره خاص است.",
  "Kate is a woman who is running from her past.": "کیت زنی است که در حال فرار از گذشته‌اش است.",
  "She is strong and smart.": "او قوی و باهوش است.",
  "Sawyer is a man who tricks people for money.": "سایر مردی است که مردم را برای پول فریب می‌دهد.",
  "But deep down, he is a good person.": "اما در اعماق وجودش، او انسان خوبی است.",
  "The survivors try to find food and water.": "بازماندگان سعی می‌کنند غذا و آب پیدا کنند.",
  "They also try to find a way to go home.": "آنها همچنین سعی می‌کنند راهی برای بازگشت به خانه پیدا کنند.",
  "But each day, they discover new mysteries.": "اما هر روز معماهای جدیدی کشف می‌کنند.",
  "They find a door in the ground.": "آنها دری در زمین پیدا می‌کنند.",
  "Inside, there is a man named Desmond.": "در داخل آن، مردی به نام دزموند حضور دارد.",
  "He has been there for three years.": "او سه سال است که آنجاست.",
  "He has to push a button every 108 minutes.": "او باید هر ۱۰۸ دقیقه یک دکمه را فشار دهد.",
  "He says something bad will happen if he does not.": "او می‌گوید اگر این کار را نکند اتفاق بدی خواهد افتاد.",
  "They also learn about a scientific group called DHARMA.": "آنها همچنین درباره یک گروه علمی به نام دارما چیزهایی یاد می‌گیرند.",
  "These scientists did experiments on the island many years ago.": "این دانشمندان سال‌ها پیش آزمایش‌هایی در جزیره انجام دادند.",
  "I love Lost for many reasons.": "من لاست را به دلایل زیادی دوست دارم.",
  "First, the characters are not perfect.": "اول اینکه شخصیت‌ها کامل نیستند.",
  "They have all made mistakes in the past.": "همه آنها در گذشته اشتباهاتی مرتکب شده‌اند.",
  "The island gives them a second chance to be better people.": "جزیره به آنها شانس دومی برای تبدیل شدن به انسان‌های بهتر می‌دهد.",
  "Second, the show asks big questions.": "دوم اینکه این سریال سوالات بزرگی مطرح می‌کند.",
  "Are we here by accident or for a reason?": "آیا ما به طور تصادفی اینجا هستیم یا دلیلی دارد؟",
  "Can people really change?": "آیا افراد واقعاً می‌توانند تغییر کنند؟",
  "Third, the friendships are very emotional.": "سوم اینکه دوستی‌ها بسیار احساسی هستند.",
  "The characters help each other and learn to trust one another.": "شخصیت‌ها به یکدیگر کمک می‌کنند و یاد می‌گیرند به هم اعتماد کنند.",
  "The most important message of the show is: Live together, die alone.": "مهم‌ترین پیام سریال این است: با هم زندگی کنید، تنها بمیرید.",
  "This means we need each other to survive.": "این بدان معناست که ما برای زنده ماندن به یکدیگر نیاز داریم.",
  "Fourth, the island is mysterious and beautiful.": "چهارم اینکه جزیره مرموز و زیباست.",
  "I enjoy watching the adventures every episode.": "من از تماشای ماجراجویی‌های هر قسمت لذت می‌برم.",
  "Finally, the ending is hopeful and emotional.": "در نهایت، پایان سریال امیدوارکننده و احساسی است.",
  "All the characters reunite after death and find peace together.": "همه شخصیت‌ها پس از مرگ دوباره به هم می‌پیوندند و با هم به آرامش می‌رسند.",
  "For me, Lost is not just about a plane crash.": "برای من، لاست فقط درباره سقوط یک هواپیما نیست.",
  "It is about second chances.": "بلکه درباره فرصت‌های دوباره است.",
  "Every character has a difficult past.": "هر شخصیت گذشته دشواری دارد.",
  "They feel guilty or broken.": "آنها احساس گناه یا شکستگی می‌کنند.",
  "But the island helps them face their problems and find forgiveness.": "اما جزیره به آنها کمک می‌کند تا با مشکلاتشان روبرو شوند و بخشش را پیدا کنند.",
  "In conclusion, Lost is my favorite TV show because it is exciting, emotional, and meaningful.": "در نتیجه، لاست سریال تلویزیونی مورد علاقه من است زیرا هیجان‌انگیز، احساسی و معنادار است.",
  "I recommend this show to everyone.": "من این سریال را به همه پیشنهاد می‌کنم.",
  "It will make you think about life and what really matters.": "این سریال شما را وادار می‌کند به زندگی و چیزهای واقعاً مهم فکر کنید.",
  "Thank you for listening.": "از اینکه گوش دادید متشکرم."
}

path = "cache/translations.json"
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)

for eng, fa in correct_translations.items():
    if eng in data:
        data[eng] = fa
    else:
        # also update cache/phrases.json if needed
        data[eng] = fa

with open(path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("Translations fixed.")
