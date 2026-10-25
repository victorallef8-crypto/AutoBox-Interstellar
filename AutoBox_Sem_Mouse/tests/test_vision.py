"""Verifica o detector com OpenCV real, sem controlar o jogo."""
import sys
import unittest
from pathlib import Path
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision import locate_boxes

class VisionTests(unittest.TestCase):
    def sample(self):
        image = np.zeros((41,41,3),np.uint8)
        cv2.circle(image,(20,20),9,(110,60,20),-1)
        cv2.circle(image,(20,20),7,(20,145,240),-1)
        cv2.circle(image,(20,20),4,(255,255,255),-1)
        cv2.line(image,(14,15),(16,23),(200,150,80),2)
        return image
    def test_box_reduced_to_33_percent(self):
        sample=self.sample()
        small=cv2.resize(sample,(14,14),interpolation=cv2.INTER_LINEAR)
        frame=np.zeros((180,260,3),np.uint8)
        frame[70:84,140:154]=small
        matches=locate_boxes(frame,sample,threshold=.82)
        self.assertTrue(any(abs(x-147)<=3 and abs(y-77)<=3 for x,y,_ in matches),matches)
    def test_relearned_small_box_is_detected_without_full_size_background(self):
        small=cv2.resize(self.sample(),(14,14))
        sample=np.zeros((31,31,3),np.uint8)
        sample[8:22,8:22]=small
        frame=np.random.default_rng(1).integers(0,25,(180,260,3),dtype=np.uint8)
        frame[70:84,140:154]=small
        matches=locate_boxes(frame,sample,threshold=.9)
        self.assertTrue(any(abs(x-147)<=3 and abs(y-77)<=3 for x,y,_ in matches),matches)
    def large_structure_with_box_like_glow(self):
        frame=np.zeros((260,400,3),np.uint8)
        cv2.rectangle(frame,(172,100),(300,200),(60,60,60),-1)
        frame[130:171,130:171]=self.sample()
        cv2.line(frame,(159,150),(180,150),(60,60,60),2)
        return frame

    def test_glow_attached_to_large_structure_is_not_a_box(self):
        frame=self.large_structure_with_box_like_glow()
        # A versao anterior dava 0.998 de correlacao nesse brilho.
        self.assertEqual(locate_boxes(frame,self.sample(),threshold=.9),[])

    def test_real_box_beside_large_structure_is_kept(self):
        frame=self.large_structure_with_box_like_glow()
        frame[60:101,60:101]=self.sample()
        matches=locate_boxes(frame,self.sample(),threshold=.9)
        self.assertEqual(len(matches),1,matches)
        self.assertTrue(abs(matches[0][0]-80)<=2 and abs(matches[0][1]-80)<=2,matches)

    def test_lower_threshold_does_not_disable_structure_rejection(self):
        self.assertEqual(locate_boxes(self.large_structure_with_box_like_glow(),
                                     self.sample(),threshold=.82),[])

    def test_blank_sample_has_no_matches(self):
        self.assertEqual(locate_boxes(np.zeros((90,90,3),np.uint8),np.zeros((31,31,3),np.uint8)),[])
    def test_blank_scene_has_no_boxes(self):
        self.assertEqual(locate_boxes(np.zeros((90,90,3),np.uint8),self.sample()),[])
    def test_off_center_learning_click_keeps_object_center(self):
        sample=np.zeros((41,41,3),np.uint8)
        patch=self.sample()[8:33,8:33]
        sample[4:29,12:37]=patch
        frame=np.zeros((100,160,3),np.uint8)
        frame[40:65,80:105]=patch
        self.assertTrue(any(abs(x-92)<=2 and abs(y-52)<=2 for x,y,_ in locate_boxes(frame,sample)))

if __name__ == "__main__": unittest.main()
