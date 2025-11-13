import argparse
import json
import random
import re
import time
from typing import Dict, List, Optional, Set

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright


def wait_for_network_idle(page: Page, timeout_ms: int = 3000) -> None:
    start = time.time()
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass
    finally:
        _ = start


def open_new_context(playwright: Playwright, headless: bool) -> BrowserContext:
    chromium = playwright.chromium
    browser = chromium.launch(headless=headless)
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    context = browser.new_context(
        user_agent=user_agent,
        viewport={"width": 1366, "height": 800},
        locale="ko-KR",
        timezone_id="Asia/Seoul",
        device_scale_factor=1.0,
        has_touch=False,
    )
    return context


def human_delay(base_delay_ms: int = 500) -> None:
    jitter = random.randint(0, base_delay_ms)
    time.sleep((base_delay_ms + jitter) / 1000.0)


def slow_scroll(page: Page, steps: int = 6, step_px: int = 800, base_delay_ms: int = 300) -> None:
    for _ in range(steps):
        page.evaluate("step => window.scrollBy(0, step)", step_px)
        human_delay(base_delay_ms)


def extract_specs_from_detail(page: Page) -> Dict[str, str]:
    specs: Dict[str, str] = {}

    def add_or_append_spec(key: str, value: str) -> None:
        if key == value:
            return
        if key in specs:
            if specs[key] == value:
                return
            if value in specs[key]:
                return
            if specs[key] in value:
                return
            existing_values = [v.strip() for v in specs[key].split(",")]
            if value.strip() not in existing_values:
                specs[key] = f"{specs[key]},{value}"
        else:
            specs[key] = value

    all_tr_elements = page.locator("tr").all()
    for tr in all_tr_elements:
        try:
            ths = tr.locator("th").all()
            tds = tr.locator("td").all()

            if len(ths) == 1 and len(tds) > 1:
                try:
                    parent_key = ths[0].inner_text().strip()
                    for td in tds:
                        value = td.inner_text().strip()
                        if value and value not in ["○", "O", "o", "●"]:
                            add_or_append_spec(parent_key, value)
                except Exception:
                    pass

            for i in range(min(len(ths), len(tds))):
                try:
                    key = ths[i].inner_text().strip()
                    value = tds[i].inner_text().strip()
                    if not key:
                        continue
                    value = value.split("인증번호 확인")[0].strip()
                    value = value.split("바로가기")[0].strip()
                    value = re.sub(r"\s*\([^)]*\)", "", value)
                    if value:
                        add_or_append_spec(key, value)
                except Exception:
                    continue
        except Exception:
            continue

    return specs


def collect_product_links_from_category(page: Page, max_per_page: Optional[int]) -> List[str]:
    selectors = [
        "li.prod_item div.prod_info a.prod_link",
        "li.prod_item .prod_name a",
        "div.prod_info a.prod_link",
        "a[href*='/product/']",
        "a[href*='product/view.html']",
    ]
    links: List[str] = []
    seen: Set[str] = set()
    for selector in selectors:
        if page.locator(selector).count() == 0:
            continue
        for a in page.locator(selector).all():
            try:
                href = a.get_attribute("href")
            except Exception:
                continue
            if not href:
                continue
            if href.startswith("javascript:"):
                continue
            if "danawa" not in href and not href.startswith("/"):
                continue
            if href in seen:
                continue
            seen.add(href)
            links.append(href)
            if max_per_page and len(links) >= max_per_page:
                return links
    return links


def paginate_category(page: Page, current_url: str, page_num: int) -> bool:
    try:
        page_buttons = page.locator(f"a.num[onclick*='movePage({page_num})']")
        if page_buttons.count() > 0:
            page_buttons.first.click()
            wait_for_network_idle(page)
            return True

        if page.evaluate("typeof movePage === 'function'"):
            page.evaluate(f"movePage({page_num})")
            wait_for_network_idle(page)
            return True

        next_group = page.locator(
            "a.edge_nav.nav_next, a[class*='nav_next'], a[onclick*='movePage']"
        ).last
        if next_group.count() > 0:
            next_group.click()
            wait_for_network_idle(page)
            page_buttons = page.locator(f"a.num[onclick*='movePage({page_num})']")
            if page_buttons.count() > 0:
                page_buttons.first.click()
                wait_for_network_idle(page)
                return True

        print(f"  movePage({page_num}) 실패 — 페이지 버튼 또는 함수 호출 불가.")
        return False
    except Exception as e:
        print(f"  페이지네이션 중 오류 발생: {e}")
        return False


def learn_checkmark_patterns(
    category_url: str,
    max_pages: int,
    max_items_per_page: Optional[int],
    headless: bool,
    max_total_items: Optional[int],
    base_delay_ms: int,
) -> List[str]:
    print("\n=== PASS 1: 데이터 구조 학습 중 ===")
    checkmark_items: List[str] = []

    with sync_playwright() as p:
        context = open_new_context(p, headless=headless)
        page = context.new_page()
        page.set_default_timeout(10000)

        page.goto(category_url, wait_until="domcontentloaded", timeout=30000)
        wait_for_network_idle(page)
        slow_scroll(page)
        human_delay(base_delay_ms)

        items_scanned = 0

        for page_index in range(max_pages):
            try:
                print(f"  페이지 {page_index + 1}/{max_pages} 스캔 중...")
                product_links = collect_product_links_from_category(page, max_items_per_page)
                print(f"    - {len(product_links)}개 링크 발견")
                if not product_links:
                    break

                for link in product_links:
                    if max_total_items and items_scanned >= max_total_items:
                        break
                    try:
                        detail_page = context.new_page()
                        detail_page.set_default_timeout(15000)
                        detail_page.goto(link, wait_until="domcontentloaded", timeout=15000)
                        wait_for_network_idle(detail_page)

                        specs = extract_specs_from_detail(detail_page)
                        for key, value in specs.items():
                            if value.strip() in ["○", "O", "o", "●"] and key not in checkmark_items:
                                checkmark_items.append(key)

                        detail_page.close()
                        items_scanned += 1
                    except Exception as e:
                        print(f"    경고: {link[:50]}... 스캔 실패 - {e}")
                        continue

                if max_total_items and items_scanned >= max_total_items:
                    break

                if page_index < max_pages - 1:
                    next_page_num = page_index + 2
                    moved = paginate_category(page, category_url, next_page_num)
                    if not moved:
                        break
                    slow_scroll(page)
                    human_delay(base_delay_ms)
            except Exception as e:
                print(f"    페이지 {page_index + 1} 스캔 중 오류: {e}")
                continue

        context.browser.close()

    print(f"  [완료] {items_scanned}개 상품 스캔 완료, {len(checkmark_items)}개 체크마크 항목 발견")
    return checkmark_items


def analyze_and_create_mapping(checkmark_items: List[str]) -> Dict[str, str]:
    print("\n=== 패턴 분석 중 ===")
    # 현재는 카테고리별 규칙이 정해지지 않았으므로, 체크마크 키 목록만 제공한다.
    print(f"  총 {len(checkmark_items)}개의 체크마크 항목을 수집했습니다.")
    if checkmark_items:
        preview = ", ".join(checkmark_items[:10])
        suffix = f" ... 외 {len(checkmark_items) - 10}개" if len(checkmark_items) > 10 else ""
        print(f"  예시: {preview}{suffix}")
    # 향후 카테고리별 매핑 규칙이 확정되면 이 부분에서 매핑을 생성하도록 확장 예정.
    return {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Danawa category pattern learner (PASS1 전용)")
    parser.add_argument("--category-url", required=True, help="Danawa category URL (list view)")
    parser.add_argument("--pages", type=int, default=1, help="Max pages to scan in PASS1")
    parser.add_argument("--items-per-page", type=int, default=0, help="Max items per page (0 for all)")
    parser.add_argument("--max-total-items", type=int, default=0, help="Stop after N items (0=unlimited)")
    parser.add_argument("--headless", action="store_true", help="Run browser headless")
    parser.add_argument("--delay-ms", type=int, default=1000, help="Base human-like delay in ms")
    parser.add_argument(
        "--mapping-output",
        help="Output JSON filepath to store learned checkmark mapping",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    checkmark_items = learn_checkmark_patterns(
        category_url=args.category_url,
        max_pages=args.pages,
        max_items_per_page=(args.items_per_page or None),
        headless=args.headless,
        max_total_items=(args.max_total_items or None),
        base_delay_ms=args.delay_ms,
    )
    mapping = analyze_and_create_mapping(checkmark_items)

    if args.mapping_output:
        with open(args.mapping_output, "w", encoding="utf-8") as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2, sort_keys=True)
        print(f"\n[저장] 매핑 결과가 '{args.mapping_output}' 파일에 저장되었습니다.")
    else:
        print("\n[결과] 매핑 JSON:")
        print(json.dumps(mapping, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

