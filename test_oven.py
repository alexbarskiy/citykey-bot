import requests, bs4

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
url = 'https://www.citykey.com.ua/horoskop-oven/'
r = requests.get(url, headers=headers, timeout=10)
soup = bs4.BeautifulSoup(r.text, 'html.parser')

# беремо 4 абзаци після першого <h3> (вже перевірено)
h3 = soup.find('h3')
if h3:
    ps = h3.find_all_next('p')[:4]
    txt = ' '.join(p.get_text(strip=True) for p in ps)
    print(txt[:600])
else:
    print('h3 не знайдено')