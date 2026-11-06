import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from chinesepoker.profiles import ProfileStore, round_event
from chinesepoker.core.player import Player
from chinesepoker.core.card import Card


def event(ident, points=3, session='s1', settled=True, mode='cpu', was_fl=False, tier=0):
    return dict(round_id=uuid4().hex,session_id=session,mode=mode,occurred_at='2026-10-22T10:00:00+00:00',
                settled=settled,players=[dict(profile_id=ident,points=points,foul=False,was_fl=was_fl,
                entered_fl=bool(tier and not was_fl),continued_fl=bool(tier and was_fl),next_tier=tier)])


def board(player, top='SQ HQ D2', mid='C4 S5 H6 D7 C8', bot='S9 H10 DJ CQ SK'):
    for row, text in zip(('top','mid','bot'),(top,mid,bot)):
        setattr(player,row,[Card(c[0],c[1:]) for c in text.split()])


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'accounts.sqlite3'
        self.store=ProfileStore(self.path)
        self.addCleanup(self.store.close)
        self.ident=self.store.create('ひかる')

    def test_names_selections_and_reopen(self):
        ascii_id=self.store.create('Ａlice')
        with self.assertRaises(ValueError): self.store.create(' alice ')
        for name in ('',' '*2,'a'*21,'abc\nxyz'):
            with self.assertRaises(ValueError): self.store.create(name)
        self.store.select(0,self.ident)
        with self.assertRaises(ValueError): self.store.select(1,self.ident)
        self.store.select(1,ascii_id)
        second=ProfileStore(self.path)
        try:
            self.assertEqual(second.selected(),(self.ident,ascii_id))
            self.assertIn('ひかる',[p['name'] for p in second.profiles()])
        finally: second.close()

    def test_fl_entry_continuation_session_and_duplicate(self):
        first=event(self.ident,points=3,settled=False,tier=14)
        self.store.record_round(first)
        self.store.record_round(first)
        self.assertEqual(self.store.stats(self.ident,'cpu')['sessions'],0)
        self.store.record_round(event(self.ident,points=7,settled=False,was_fl=True,tier=14))
        self.store.record_round(event(self.ident,points=-2,was_fl=True))
        s=self.store.stats(self.ident,'cpu')
        self.assertEqual((s['hands'],s['wins'],s['losses'],s['points']),(3,2,1,8))
        self.assertEqual((s['sessions'],s['session_wins'],s['settled_points']),(1,1,8))
        self.assertEqual((s['normal_hands'],s['fl_hands'],s['fl_entries'],s['fl_continues']),(1,2,1,1))
        self.assertEqual(s['tiers'][14],1)

    def test_pvp_is_atomic_and_separate_from_cpu(self):
        other=self.store.create('相手')
        e=event(self.ident,mode='pvp')
        e['players'].append(dict(e['players'][0],profile_id=other,points=-3))
        self.store.record_round(e)
        self.assertEqual(self.store.stats(self.ident,'pvp')['points'],3)
        self.assertEqual(self.store.stats(other,'pvp')['points'],-3)
        self.assertEqual(self.store.stats(self.ident,'cpu')['hands'],0)
        broken=event(self.ident,session='s2',mode='pvp')
        broken['players'].append(dict(broken['players'][0],profile_id='missing'))
        with self.assertRaises(sqlite3.IntegrityError): self.store.record_round(broken)
        self.assertEqual(self.store.stats(self.ident,'pvp')['hands'],1)
        self.assertFalse(self.store.db.execute('SELECT 1 FROM rounds WHERE id=?',(broken['round_id'],)).fetchone())

    def test_abandoned_session_does_not_become_a_win(self):
        self.store.record_round(event(self.ident,points=50,settled=False,tier=17))
        self.store.record_round(event(self.ident,points=-3,session='new'))
        s=self.store.stats(self.ident,'cpu')
        self.assertEqual((s['points'],s['settled_points'],s['session_losses']),(47,-3,1))

    def test_two_connections_no_lost_results(self):
        other=ProfileStore(self.path)
        try:
            self.store.record_round(event(self.ident,points=3))
            other.record_round(event(self.ident,points=-3,session='s2'))
            self.assertEqual(self.store.stats(self.ident,'cpu')['sessions'],2)
            self.assertEqual(other.stats(self.ident,'cpu')['points'],0)
        finally: other.close()

    def test_foul_and_draw_with_no_fl_and_guest(self):
        player=Player('p'); opponent=Player('guest')
        board(player,top='SA HA DA',mid='C2 S3 H4 D7 C8')
        board(opponent)
        player.evaluate_board(); opponent.evaluate_board()
        e=round_event('r','s','pvp',(self.ident,None),(player,opponent),(0,0),False)
        self.store.record_round(e)
        s=self.store.stats(self.ident,'pvp')
        self.assertEqual((s['fouls'],s['draws'],s['fl_entries']),(1,1,0))
        self.assertEqual(len(e['players']),1)
        with self.assertRaises(ValueError):
            round_event('r2','s','cpu',(self.ident,None),(Player('empty'),opponent),(0,0),True)


try:
    import pygame
except ImportError:
    pygame=None


@unittest.skipIf(pygame is None,'Pygame required')
class ProfileGuiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'profiles.sqlite3'
        self.store=ProfileStore(self.path)
        self.addCleanup(self.store.close)
        self.ident=self.store.create('テスト利用者')

    def test_gui_records_exact_score_once_and_retries_failed_save(self):
        from chinesepoker.ui.gui import GameGUI
        gui=GameGUI(profile_store=self.store,profile_ids=(self.ident,None))
        self.addCleanup(gui.close)
        board(gui.p1)
        board(gui.p2,top='S2 H3 D4',mid='C5 S6 H7 D8 C9',bot='S10 HJ DQ CK SA')
        gui.actions=[{'type':'eval'}]
        with patch.object(self.store,'record_round',side_effect=sqlite3.OperationalError('disk full')):
            gui.next_action()
        expected=gui.game.points[gui.p1.name]
        self.assertIsNotNone(gui.save_error)
        self.assertFalse(gui.can_return_to_menu())
        with self.assertRaises(RuntimeError): gui.build_round_actions()
        self.assertEqual(self.store.stats(self.ident,'cpu')['hands'],0)
        gui.save_result()
        gui.save_result()
        gui.next_action()
        s=self.store.stats(self.ident,'cpu')
        self.assertEqual((s['hands'],s['points'],s['fl_entries']),(1,expected,1))
        self.assertEqual(s['sessions'],0)
        first_session=gui.session_id
        gui.show_results=False
        gui.build_round_actions()
        self.assertEqual(first_session,gui.session_id)
        board(gui.p1,top='S2 H3 D4',mid='C5 S6 H7 D8 C9',bot='S10 HJ DQ CK SA')
        board(gui.p2,top='H2 D3 C4',mid='S5 H6 D7 C8 S9',bot='H10 DJ CQ SK HA')
        gui.target_reached=True
        gui.actions=[{'type':'eval'}]
        gui.next_action()
        s=self.store.stats(self.ident,'cpu')
        self.assertEqual(s['sessions'],1)
        self.assertEqual(s['settled_points'],gui.game.points[gui.p1.name])
        gui.build_round_actions()
        self.assertNotEqual(first_session,gui.session_id)

    def test_guest_and_unfinished_game_do_not_record(self):
        from chinesepoker.ui.gui import GameGUI
        gui=GameGUI(profile_store=self.store,profile_ids=(self.ident,None))
        gui.close()
        self.assertEqual(self.store.stats(self.ident,'cpu')['hands'],0)
        guest=GameGUI(profile_store=self.store)
        self.addCleanup(guest.close)
        board(guest.p1); board(guest.p2)
        guest.actions=[{'type':'eval'}]
        guest.next_action()
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM rounds').fetchone()[0],0)

    def test_ui_starters_select_stats_and_restart(self):
        from chinesepoker.ui.accounts import AccountMenu
        from chinesepoker.ui.gui import screen
        self.store.ensure_test_profiles()
        ui=AccountMenu(self.store)
        self.assertEqual(ui.page,'profiles')
        ui.draw(screen)
        ui.choose('starter-1')
        self.assertEqual(self.store.balance('starter-1'),1050)
        self.store.record_round(event('starter-1'))
        ui.open_stats(0)
        self.assertEqual(ui.snapshot['hands'],1)
        ui.draw(screen)
        ui.page='home'
        ui.draw_home(screen)
        reopened=AccountMenu(self.store)
        self.assertEqual(reopened.selected[0],'starter-1')
        self.assertEqual(self.store.balance('starter-1'),1050)

    def test_threshold_waits_for_fl_and_retains_trigger(self):
        from chinesepoker.ui.gui import GameGUI
        gui=GameGUI(profile_store=self.store,profile_ids=(self.ident,None))
        self.addCleanup(gui.close)
        def resolve(score, fl):
            gui.game.points={gui.p1.name:score,gui.p2.name:-score}
            gui.p1.next_fantasyland=fl
            gui.p2.next_fantasyland=False
            return 'test'
        for score,fl,finished in [(99,False,False),(101,True,False),(85,False,True)]:
            board(gui.p1); board(gui.p2)
            gui.actions=[{'type':'eval'}]
            with patch.object(gui.game,'resolve_scores',side_effect=lambda:resolve(score,fl)):
                gui.next_action()
            self.assertEqual(gui.session_settled,finished)
            if not finished:
                gui.build_round_actions()
        self.assertEqual(self.store.balance(self.ident),1085)
        self.assertEqual(self.store.stats(self.ident,'cpu')['sessions'],1)
        gui.save_result()
        self.assertEqual(self.store.balance(self.ident),1085)
        gui.build_round_actions()
        self.assertEqual(gui.game.points[gui.p1.name],0)
        self.assertFalse(gui.target_reached)


class CurrencyTests(unittest.TestCase):
    def test_starters_daily_and_atomic_match_rewards(self):
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profiles.sqlite3'
            store=ProfileStore(path)
            store.ensure_test_profiles();store.ensure_test_profiles()
            self.assertEqual(len(store.profiles()),3)
            a,b='starter-1','starter-2'
            self.assertEqual(store.balance(a),1000)
            before=datetime(2026,10,22,14,59,tzinfo=timezone.utc)
            after=datetime(2026,10,22,15,0,tzinfo=timezone.utc)
            self.assertEqual(store.claim_daily(a,before),50)
            self.assertEqual(store.claim_daily(a,before),0)
            self.assertEqual(store.claim_daily(a,after),50)
            self.assertEqual(store.claim_daily(a,before),0)
            e=event(a,points=105,mode='pvp');e['coin_match']=True
            e['players']+=event(b,points=-105)['players']
            store.record_round(e);store.record_round(e)
            self.assertEqual((store.balance(a),store.balance(b)),(1205,900))
            unfinished=event(a,points=5,session='s2',settled=False);unfinished['coin_match']=True
            store.record_round(unfinished)
            self.assertEqual(store.balance(a),1205)
            broken=event(a,points=100,session='s3');broken['coin_match']=True
            broken['players']+=event('missing',points=-100)['players']
            with self.assertRaises(sqlite3.IntegrityError):store.record_round(broken)
            self.assertEqual(store.balance(a),1205)
            store.close()
            store=ProfileStore(path)
            self.assertEqual(store.balance(a),1205)
            store.close()

    def test_rewards_use_final_positive_score_and_fixed_loss(self):
        with tempfile.TemporaryDirectory() as folder:
            store=ProfileStore(Path(folder)/'profiles.sqlite3')
            ident=store.create('rewards')
            for score,change in [(123,123),(250,250),(85,85),(-123,-100),(-250,-100),(-20,-100),(0,0)]:
                with self.subTest(score=score):
                    before=store.balance(ident)
                    result=event(ident,points=score,session=uuid4().hex)
                    result['coin_match']=True
                    store.record_round(result)
                    store.record_round(result)
                    self.assertEqual(store.balance(ident),before+change)
            store.close()

    def test_v1_migration_preserves_history_without_retroactive_rewards(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'profiles.sqlite3'
            store=ProfileStore(path);ident=store.create('existing')
            store.record_round(event(ident))
            store.db.executescript('DROP TABLE coin_entries; DROP TABLE wallets; PRAGMA user_version=1;')
            store.close()
            store=ProfileStore(path)
            self.assertEqual(store.balance(ident),1000)
            self.assertEqual(store.stats(ident,'cpu')['sessions'],1)
            store.close()


if __name__=='__main__': unittest.main()
