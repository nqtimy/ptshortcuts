"""PT Shortcuts — Pro Tools Keyboard Trainer.

A Cookie Clicker-style game to learn Pro Tools keyboard shortcuts.
"""

import sys
import time

import pygame

from game.config import DEFAULT_WIDTH, DEFAULT_HEIGHT, MIN_WIDTH, MIN_HEIGHT, FPS, BG_COLOR, TEXT_PRIMARY
from game.keyboard import KeyboardHandler
from game.loader import load_certifications
from game.renderer import draw_text
from game.screens import MenuScreen, GameScreen, StatsScreen, LeaderboardScreen


def main():
    pygame.init()
    pygame.display.set_caption("PT Shortcuts — Pro Tools Keyboard Trainer")

    screen = pygame.display.set_mode(
        (DEFAULT_WIDTH, DEFAULT_HEIGHT),
        pygame.RESIZABLE
    )
    clock = pygame.time.Clock()

    # Off-screen buffer for screen shake
    render_surface = pygame.Surface((DEFAULT_WIDTH, DEFAULT_HEIGHT))

    # Load certifications from shortcuts/ folder
    certifications = load_certifications()
    if not certifications:
        screen.fill(BG_COLOR)
        draw_text(screen, "Aucun fichier de certification trouve dans shortcuts/",
                  DEFAULT_WIDTH // 2, DEFAULT_HEIGHT // 2, TEXT_PRIMARY, 24, anchor="center")
        pygame.display.flip()
        pygame.time.wait(3000)
        pygame.quit()
        sys.exit(1)

    # Start keyboard handler
    kbd = KeyboardHandler()
    kbd.start()
    # Suppress Win key from OS when game window is focused (must be on main thread)
    wm_info = pygame.display.get_wm_info()
    kbd.start_win_suppression(wm_info.get('window', 0))

    # Screens
    menu = MenuScreen(certifications)
    game_screen = None
    stats_screen = None
    leaderboard_screen = None
    current_screen = 'menu'  # 'menu', 'game', 'stats', or 'leaderboard'

    running = True
    last_time = time.time()

    try:
        while running:
            now = time.time()
            dt = min(now - last_time, 0.05)
            last_time = now

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    break

                if event.type == pygame.VIDEORESIZE:
                    new_w = max(MIN_WIDTH, event.w)
                    new_h = max(MIN_HEIGHT, event.h)
                    screen = pygame.display.set_mode((new_w, new_h), pygame.RESIZABLE)
                    render_surface = pygame.Surface((new_w, new_h))

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        if current_screen == 'game':
                            current_screen = 'menu'
                            game_screen = None
                            menu.selected = None
                            menu.selected_difficulty = None
                            menu.selected_custom = False
                            kbd.clear()
                        elif current_screen == 'stats':
                            current_screen = 'menu'
                            stats_screen = None
                        elif current_screen == 'leaderboard':
                            current_screen = 'menu'
                            leaderboard_screen = None
                        else:
                            running = False
                            break

                if current_screen == 'menu':
                    menu.handle_event(event)
                elif current_screen == 'game' and game_screen:
                    result = game_screen.handle_event(event)
                    if result == 'menu':
                        current_screen = 'menu'
                        game_screen = None
                        menu.selected = None
                        kbd.clear()
                elif current_screen == 'stats' and stats_screen:
                    result = stats_screen.handle_event(event)
                    if result == 'menu':
                        current_screen = 'menu'
                        stats_screen = None
                elif current_screen == 'leaderboard' and leaderboard_screen:
                    result = leaderboard_screen.handle_event(event)
                    if result == 'menu':
                        current_screen = 'menu'
                        leaderboard_screen = None

            if not running:
                break

            # Check menu → leaderboard transition
            if current_screen == 'menu' and menu.show_leaderboard:
                menu.show_leaderboard = False
                leaderboard_screen = LeaderboardScreen(certifications, menu.current_cert)
                current_screen = 'leaderboard'

            # Check menu → stats transition
            if current_screen == 'menu' and menu.show_stats:
                menu.show_stats = False
                cert_name = menu.current_cert
                if cert_name in certifications:
                    stats_screen = StatsScreen(certifications, cert_name)
                    current_screen = 'stats'

            # Check menu selection
            if current_screen == 'menu' and menu.selected:
                max_diff = menu.selected_difficulty or 3
                is_custom = menu.selected_custom
                sel = menu.selected
                # In custom mode, `selected` is a list of cert names; merge them.
                if is_custom and isinstance(sel, list) and sel:
                    all_sc = []
                    cats = []
                    for c in sel:
                        if c not in certifications:
                            continue
                        cd = certifications[c]
                        all_sc.extend(cd.get('all_shortcuts', []))
                        cats.extend(cd.get('category_names', []))
                    if all_sc:
                        merged = {'all_shortcuts': all_sc, 'category_names': cats}
                        label = sel[0] if len(sel) == 1 else "Custom"
                        # In custom mode, all difficulties are available.
                        game_screen = GameScreen(
                            label, merged, kbd,
                            max_difficulty=3,
                            custom_mode=True,
                            timer_enabled=menu.selected_timer,
                            custom_bonus=menu.selected_bonus,
                            custom_show_answer=menu.selected_show_answer,
                            custom_random=menu.selected_random,
                            no_numpad=menu.no_numpad,
                        )
                        current_screen = 'game'
                        kbd.clear()
                elif not is_custom:
                    cert_name = sel
                    if cert_name in certifications:
                        game_screen = GameScreen(
                            cert_name, certifications[cert_name], kbd,
                            max_difficulty=max_diff,
                            custom_mode=False,
                            timer_enabled=True,
                            no_numpad=menu.no_numpad,
                        )
                        current_screen = 'game'
                        kbd.clear()

            # Update
            if current_screen == 'game' and game_screen:
                game_screen.update(dt)

            # Draw with screen shake support
            sw, sh = screen.get_size()
            if render_surface.get_size() != (sw, sh):
                render_surface = pygame.Surface((sw, sh))

            if current_screen == 'menu':
                menu.draw(render_surface, dt)
                screen.blit(render_surface, (0, 0))
            elif current_screen == 'leaderboard' and leaderboard_screen:
                leaderboard_screen.draw(render_surface, dt)
                screen.blit(render_surface, (0, 0))
            elif current_screen == 'stats' and stats_screen:
                stats_screen.draw(render_surface, dt)
                screen.blit(render_surface, (0, 0))
            elif current_screen == 'game' and game_screen:
                game_screen.draw(render_surface)
                sx, sy = game_screen.get_shake_offset()
                screen.fill(BG_COLOR)
                screen.blit(render_surface, (sx, sy))

            pygame.display.flip()
            clock.tick(FPS)

    finally:
        kbd.stop_win_suppression()
        kbd.stop()
        pygame.quit()


if __name__ == '__main__':
    main()
