"""Profile selection, Unicode name entry, and local statistics screens."""
import sqlite3
from datetime import datetime
import pygame
from .gui import Button, draw_text, font, large_font, BG_COLOR, WHITE, GOLD, RED, WIDTH

MUTED = (184, 211, 196)
PANEL = (23, 65, 45)
small = pygame.font.SysFont('yugothic,meiryo,notosanscjk,Arial', 20)


def button(x, y, w, text):
    return Button(x, y, w, 48, text, (0, 100, 142), (0, 133, 179))


def fit(text, width, face=font):
    if face.size(text)[0] <= width:
        return text
    while text and face.size(text+'…')[0] > width:
        text=text[:-1]
    return text+'…'


def rate(count, total):
    return f'{100*count/total:.1f}%' if total else '—'


class AccountMenu:
    def __init__(self, store, error=None):
        self.store = store
        self.page = 'home'
        self.target = 0
        self.offset = 0
        self.name = ''
        self.composition = ''
        self.typing = False
        self.mode = 'cpu'
        self.message = ''
        self.storage_error = error
        self.selected = store.selected() if store else (None,None)
        self.people = store.profiles() if store else []
        self.snapshot = None
        self.slot_buttons = [button(275,520+i*70,500,'') for i in range(2)]
        self.stat_buttons = [button(800,520+i*70,200,'成績を見る') for i in range(2)]
        self.back = button(90,800,180,'戻る')
        self.guest = button(930,800,240,'ゲストで遊ぶ')
        self.prev = button(90,590,180,'前のページ')
        self.next = button(930,590,240,'次のページ')
        self.input_rect = pygame.Rect(90,665,810,52)
        self.create_button = button(930,665,240,'作成して選択')
        self.cpu = button(90,125,230,'CPU対戦')
        self.pvp = button(335,125,230,'2人対戦')

    def name_of(self, ident):
        return next((p['name'] for p in self.people if p['id']==ident), 'ゲスト')

    def stop_input(self):
        pygame.key.stop_text_input()
        self.typing = False
        self.composition = ''

    def open_profiles(self, seat):
        self.target = seat
        self.offset = 0
        self.page = 'profiles'
        self.message = ''
        self.name = ''
        self.people = self.store.profiles()

    def choose(self, ident):
        self.store.select(self.target, ident)
        self.selected = self.store.selected()
        self.page = 'home'
        self.message = ''
        self.stop_input()

    def open_stats(self, seat):
        ident = self.selected[seat]
        if ident is None:
            self.message = '名前を登録すると成績を保存できます。'
            return
        self.target = seat
        self.mode = 'cpu' if seat==0 else 'pvp'
        self.snapshot = self.store.stats(ident, self.mode)
        self.page = 'stats'
        self.message = ''

    def rows(self):
        return [(button(90,195+i*62,1080,fit(p['name'],1000)),p['id'])
                for i,p in enumerate(self.people[self.offset:self.offset+6])]

    def handle_event(self, event):
        try:
            return self._handle_event(event)
        except (sqlite3.Error, OSError):
            self.message = '保存データを読み書きできません。保存先の空き容量・権限を確認してください。'
        except ValueError as error:
            self.message = str(error)
        return True

    def _handle_event(self, event):
        if self.page == 'home':
            for i,b in enumerate(self.slot_buttons):
                if b.is_clicked(event):
                    if self.store:
                        self.open_profiles(i)
                    return True
            for i,b in enumerate(self.stat_buttons):
                if b.is_clicked(event):
                    if self.store:
                        self.open_stats(i)
                    return True
            return False
        if (event.type==pygame.KEYDOWN and event.key==pygame.K_ESCAPE) or self.back.is_clicked(event):
            self.page = 'home'
            self.message = ''
            self.stop_input()
            return True
        if self.page == 'stats':
            for b,mode in ((self.cpu,'cpu'),(self.pvp,'pvp')):
                if b.is_clicked(event):
                    snapshot = self.store.stats(self.selected[self.target], mode)
                    self.mode, self.snapshot = mode, snapshot
            return True
        if self.typing and event.type==pygame.TEXTINPUT:
            self.name = (self.name+event.text)[:20]
            self.composition = ''
        elif self.typing and event.type==pygame.TEXTEDITING:
            self.composition = event.text
        elif self.typing and event.type==pygame.KEYDOWN and event.key==pygame.K_BACKSPACE:
            if not self.composition:
                self.name = self.name[:-1]
        if event.type==pygame.MOUSEBUTTONDOWN and event.button==1 and self.input_rect.collidepoint(event.pos):
            self.typing = True
            pygame.key.start_text_input()
            pygame.key.set_text_input_rect(self.input_rect)
        if self.create_button.is_clicked(event):
            if self.composition:
                self.message = '日本語入力を確定してから作成してください。'
            else:
                ident = self.store.create(self.name)
                self.people = self.store.profiles()
                self.choose(ident)
        if self.guest.is_clicked(event):
            self.choose(None)
        if self.prev.is_clicked(event):
            self.offset = max(0,self.offset-6)
        if self.next.is_clicked(event) and self.offset+6<len(self.people):
            self.offset += 6
        for b,ident in self.rows():
            if b.is_clicked(event):
                self.choose(ident)
                break
        return True

    def draw_home(self, surface):
        draw_text(surface, 'アカウントの選択・作成', font, GOLD, WIDTH//2, 480, 'center')
        for i,b in enumerate(self.slot_buttons):
            b.text = fit(f'Player {i+1}  /  {self.name_of(self.selected[i])}',460)
            b.draw(surface)
            self.stat_buttons[i].draw(surface)
        draw_text(surface, 'CPU戦ではPlayer 1を記録。2人対戦では選択した両者を記録。', small, MUTED, WIDTH//2, 680, 'center')
        draw_text(surface, 'ゲストの成績は保存されません。アカウントはこのPC内だけで利用できます。', small, MUTED, WIDTH//2, 715, 'center')
        if self.storage_error:
            draw_text(surface, '成績保存を利用できません。今回はゲストとして遊べます。', small, RED, WIDTH//2, 760, 'center')
        elif self.message:
            draw_text(surface, fit(self.message,1100,small), small, GOLD, WIDTH//2, 760, 'center')

    def draw(self, surface):
        surface.fill(BG_COLOR)
        if self.page == 'profiles':
            draw_text(surface, f'Player {self.target+1} のアカウント', large_font, WHITE, 90, 60)
            draw_text(surface, '名前を選択するか、新しいアカウントを作成してください。', font, MUTED, 90, 125)
            for b,ident in self.rows():
                if ident == self.selected[self.target]:
                    b.color = (125,105,24)
                b.draw(surface)
            if not self.people:
                draw_text(surface, 'まだアカウントがありません。下の欄に名前を入力してください。', font, GOLD, 90, 225)
            self.prev.draw(surface)
            self.next.draw(surface)
            draw_text(surface, f'{self.offset//6+1} / {max(1,(len(self.people)+5)//6)}',font,WHITE,640,610,'center')
            draw_text(surface, '新しい名前（1～20文字・日本語可）', small, MUTED, 90, 640)
            pygame.draw.rect(surface,PANEL,self.input_rect,border_radius=6)
            pygame.draw.rect(surface,GOLD if self.typing else WHITE,self.input_rect,2,border_radius=6)
            draw_text(surface,fit(self.name+self.composition,780),font,WHITE,105,675)
            self.create_button.draw(surface)
            self.guest.draw(surface)
        else:
            self.draw_stats(surface)
        self.back.draw(surface)
        if self.message:
            draw_text(surface,fit(self.message,1100,small),small,RED,90,735)

    def draw_stats(self, surface):
        s = self.snapshot
        draw_text(surface,fit(self.name_of(self.selected[self.target])+' の成績',1100,large_font),large_font,WHITE,90,55)
        for b,mode in ((self.cpu,'cpu'),(self.pvp,'pvp')):
            b.color = (125,105,24) if mode==self.mode else (0,100,142)
            b.draw(surface)
        metrics = [
            ('完了対局',f'{s["sessions"]} 対局'),
            ('対局の勝率',rate(s['session_wins'],s['sessions'])),
            ('対局の勝 / 敗 / 分',f'{s["session_wins"]} / {s["session_losses"]} / {s["session_draws"]}'),
            ('完了対局の累計得点',f'{s["settled_points"]:+d} pt'),
            ('完了ハンド',f'{s["hands"]} ハンド'),
            ('ハンドの勝 / 敗 / 分',f'{s["wins"]} / {s["losses"]} / {s["draws"]}'),
            ('FL新規進入 / 進入率',f'{s["fl_entries"]} 回 / {rate(s["fl_entries"],s["normal_hands"])}'),
            ('FL継続 / 継続率',f'{s["fl_continues"]} 回 / {rate(s["fl_continues"],s["fl_hands"])}'),
            ('ファウル / ファウル率',f'{s["fouls"]} 回 / {rate(s["fouls"],s["hands"])}'),
            ('全完了ハンドの累計得点',f'{s["points"]:+d} pt'),
        ]
        for i,(label,value) in enumerate(metrics):
            x = 90+(i%2)*570
            y = 205+(i//2)*61
            draw_text(surface,label,small,MUTED,x,y)
            draw_text(surface,value,font,WHITE,x+300,y)
        tiers = ' / '.join(f'{t}枚: {s["tiers"][t]}回' for t in (14,15,16,17))
        draw_text(surface,'新規FLの内訳  '+tiers,small,GOLD,90,520)
        draw_text(surface,'最近の5ハンド（新しい順）',font,WHITE,90,565)
        if not s['recent']:
            draw_text(surface,'まだ記録がありません。選択中のアカウントで対戦してください。',small,MUTED,90,610)
        for i,r in enumerate(s['recent']):
            stamp = datetime.fromisoformat(r['occurred_at']).astimezone().strftime('%m/%d %H:%M')
            result = '勝ち' if r['points']>0 else '負け' if r['points']<0 else '引分'
            tag = 'ファウル' if r['foul'] else f'FL進入 {r["next_tier"]}枚' if r['entered_fl'] else 'FL継続' if r['continued_fl'] else 'FL終了' if r['was_fl'] else '通常'
            draw_text(surface,f'{stamp}     {result}    {r["points"]:+d} pt    {tag}',small,MUTED,90,607+i*25)
        draw_text(surface,'1対局 = 両者のFL権がなくなるまで。勝率は引分を含む完了対局が分母です。',small,MUTED,90,765)
        draw_text(surface,'進入率 = 新規FL / 通常ハンド。継続率 = FL継続 / FLハンド。',small,MUTED,320,810)
        draw_text(surface,'中断した対局も、終了済みハンドの記録は残ります。未完了ハンドは記録しません。',small,MUTED,90,862)
