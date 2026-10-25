import json
import unittest
from browser_session import WorldFeed

def snapshot():
    return {"map":{"id":"4-3","width":21000,"height":13100,"gates":[{"id":"gate","x":12,"y":20}]},
            "me":{"mapId":"4-3","x":100,"y":100,"speed":380,"hp":60,"maxHp":100,
                  "username":"private-user","group":{"membershipToken":"private-token"}},
            "boxes":[{"id":"far","revision":1,"x":300,"y":100},
                     {"id":"near","revision":2,"x":130,"y":140}],
            "npcs":[],"inputChannel":"private-channel","mapSessionId":"private-session"}

class FeedTests(unittest.TestCase):
    def setUp(self):
        self.now=1.
        self.feed=WorldFeed(clock=lambda:self.now)
        self.feed.begin("stream")
    def send(self, **kw):
        packet={"transport":"delta1","epoch":"epoch","sequence":1,"full":snapshot()}
        packet.update(kw)
        if "patch" in kw: packet.pop("full",None)
        return self.feed.ingest("stream",json.dumps(packet))
    def test_full_selects_nearest_box_not_portal(self):
        self.assertTrue(self.send())
        result=self.feed.summary()
        self.assertTrue(result["fresh"])
        self.assertEqual(result["nearest"]["id"],"near")
        self.assertEqual(result["nearest"]["distance"],50)
        self.assertEqual(result["boxes"],2)
        self.assertEqual(result["portals"],1)
        self.assertEqual(result["hp_percent"],60)
    def test_private_data_is_not_retained(self):
        self.send()
        saved=repr(vars(self.feed))
        for value in ("private-user","private-token","private-channel","private-session"):
            self.assertNotIn(value,saved)
    def test_object_patch_moves_ship_and_recomputes_nearest(self):
        self.send()
        self.assertTrue(self.send(sequence=2,base=1,patch=["o",[["me",["o",[["x",["v",290]]],[]]]],[]]))
        self.assertEqual(self.feed.summary()["nearest"]["id"],"far")
    def test_replacement_array_removes_collected_box(self):
        self.send()
        self.assertTrue(self.send(sequence=2,base=1,patch=["o",[["boxes",["v",[snapshot()["boxes"][0]]]]],[]]))
        self.assertEqual(self.feed.summary()["nearest"]["id"],"far")
    def test_sequence_gap_discards_state_until_full(self):
        self.send()
        self.assertFalse(self.send(sequence=3,base=2,patch=["o",[],[]]))
        self.assertFalse(self.feed.summary()["fresh"])
        self.assertTrue(self.send(sequence=8))
        self.assertTrue(self.feed.summary()["fresh"])
    def test_unknown_relevant_patch_fails_closed(self):
        self.send()
        self.assertFalse(self.send(sequence=2,base=1,patch=["o",[["boxes",["a",1,[]]]],[]]))
        self.assertFalse(self.feed.summary()["fresh"])
    def test_interruption_diagnostic_preserves_first_failure_without_private_values(self):
        self.send()
        patch=["o",[["boxes",["a",1,[["v",{"id":"private-id","x":130,"y":140,"token":"private-secret"}]]]]],[]]
        self.assertFalse(self.send(sequence=2,base=1,patch=patch))
        first=self.feed.diagnostic()["failure"]
        self.assertEqual(first["code"],"unsupported_patch")
        self.assertEqual(first["path"],"boxes")
        self.assertEqual(first["operation"],"a")
        self.assertEqual(first["last_sequence"],1)
        self.assertEqual(first["received_sequence"],2)
        saved=json.dumps(first)
        for value in ("private-id","private-secret","token"):
            self.assertNotIn(value,saved)
        self.send(sequence=3,base=2,patch=["o",[],[]])
        self.assertEqual(self.feed.diagnostic()["failure"],first)
        self.send(sequence=4)
        self.assertIsNone(self.feed.diagnostic()["failure"])
        self.assertTrue(self.feed.summary()["fresh"])

    def test_unknown_irrelevant_patch_does_not_break_navigation(self):
        self.send()
        self.assertTrue(self.send(sequence=2,base=1,patch=["o",[["chat",["unknown","private"]]],[]]))
        self.assertTrue(self.feed.summary()["fresh"])
        self.assertNotIn("private",repr(self.feed.state))
    def test_duplicate_does_not_refresh_old_data(self):
        self.send()
        self.now=4
        self.assertFalse(self.send())
        self.assertFalse(self.feed.summary()["fresh"])
        self.assertNotIn("nearest",self.feed.summary())
    def test_new_connection_cannot_reuse_previous_state(self):
        self.send()
        self.feed.begin("new")
        self.assertFalse(self.feed.summary()["fresh"])
        self.assertFalse(self.send())
    def test_new_epoch_patch_requires_full(self):
        self.send()
        self.assertFalse(self.send(epoch="next",sequence=2,base=1,patch=["o",[],[]]))
        self.assertFalse(self.feed.summary()["fresh"])
    def test_deleted_position_is_not_reported_ready(self):
        self.send()
        self.send(sequence=2,base=1,patch=["o",[["me",["o",[],["x"]]]],[]])
        self.assertFalse(self.feed.summary()["fresh"])
    def test_boxes_outside_map_are_not_candidates(self):
        full=snapshot()
        full["boxes"]=[{"id":"invalid","x":-1,"y":100}]
        self.send(full=full)
        self.assertIsNone(self.feed.summary()["nearest"])
    def test_map_transition_is_not_ready(self):
        full=snapshot(); full["me"]["mapId"]="other"
        self.send(full=full)
        self.assertFalse(self.feed.summary()["fresh"])
    def test_matching_stream_close_invalidates(self):
        self.send()
        self.feed.end("another")
        self.assertTrue(self.feed.summary()["fresh"])
        self.feed.end("stream")
        self.assertFalse(self.feed.summary()["fresh"])
    def test_malformed_message_does_not_escape(self):
        self.send()
        self.assertFalse(self.feed.ingest("stream","{"))
        self.assertFalse(self.feed.summary()["fresh"])
    def test_patch_is_atomic(self):
        self.send()
        self.send(sequence=2,base=1,patch=["o",[["me",["o",[["x",["v",200]]],[]]],["boxes",["bad"]]],[]])
        self.assertIsNone(self.feed.state)

if __name__=="__main__": unittest.main()
