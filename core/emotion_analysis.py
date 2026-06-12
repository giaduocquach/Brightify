import logging
import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
from typing import Dict, List, Tuple, Optional
from transformers import AutoModel, AutoTokenizer
import re
from collections import defaultdict
from pyvi import ViTokenizer

logger = logging.getLogger(__name__)


class VietnameseEmotionLexicon:
    """Expanded Vietnamese emotion lexicon (500+ entries).
    
    Sources & references:
    - VLSP Shared Task on Sentiment Analysis (2016, 2018)
    - UIT-VSMEC: Vietnamese Social Media Emotion Corpus (Huynh et al., 2019)
    - Palmer et al. (2013) Russell's Circumplex Model color-emotion mapping
    - Vietnamese NLP community word lists (vi.wiktionary.org)
    - Manual curation for Vietnamese music-specific phrases and Gen Z slang
    
    Each emotion category maps to valence-arousal coordinates:
      happy:      V=0.8,  A=0.6   (high valence, moderate arousal)
      sad:        V=0.2,  A=0.3   (low valence, low arousal)
      love:       V=0.7,  A=0.5   (high valence, moderate arousal)
      angry:      V=0.3,  A=0.8   (low valence, high arousal)
      peaceful:   V=0.6,  A=0.2   (moderate valence, low arousal)
      excited:    V=0.8,  A=0.9   (high valence, high arousal)
      melancholic: V=0.35, A=0.4  (low-moderate valence, low-moderate arousal)
      longing:    V=0.4,  A=0.5   (low-moderate valence, moderate arousal)
      hope:       V=0.7,  A=0.6   (high valence, moderate-high arousal)
    """

    def __init__(self):
        # Emotion categories based on Russell's model + music-specific emotions
        self.emotion_words = {
            'happy': [
                # Core happy words
                'vui', 'hạnh phúc', 'vui vẻ', 'vui sướng', 'phấn khích', 'hân hoan',
                'rạng rỡ', 'tươi cười', 'vui mừng', 'sung sướng',
                'vui tươi', 'rộn ràng', 'hồ hởi', 'phơi phới', 'thoải mái',
                'yêu đời', 'lạc quan', 'hào hứng', 'náo nức', 'thích thú',
                # Extended
                'hoan hỉ', 'mừng rỡ', 'sảng khoái', 'khoái chí', 'hớn hở',
                'tươi vui', 'phấn chấn', 'rạng ngời', 'hài lòng', 'mãn nguyện',
                'toại nguyện', 'thỏa mãn', 'thỏa lòng', 'niềm vui', 'nụ cười',
                'cười', 'cười tươi', 'cười nắng', 'cười sáng', 'tận hưởng',
                'hạnh phúc lắm', 'vui quá', 'mừng lắm', 'thú vị', 'tuyệt vời',
                # Music phrases
                'nắng vàng', 'mùa xuân', 'nắng ấm', 'bình minh', 'ngày mới',
                'tỏa sáng', 'rực rỡ', 'lung linh', 'tươi đẹp', 'rực nắng',
                # Gen Z / loanwords
                'chill', 'vibe', 'slay', 'flex', 'mood tốt', 'happy', 'enjoy',
                'amazing', 'perfect', 'wonderful', 'good vibes',
                # Regional: Southern
                'dzui', 'dzui quá', 'happy ghê',
                # Regional: Central
                'mừng rứa', 'sướng rứa',
            ],
            'sad': [
                # Core sad words
                'buồn', 'đau', 'khóc', 'cô đơn', 'lẻ loi', 'nhớ', 'thương',
                'xa', 'mất', 'lỡ', 'tiếc', 'hối hận', 'tan vỡ', 'chia ly',
                'cách biệt', 'u sầu', 'nặng lòng', 'não nề', 'sầu muộn',
                'bi thương', 'đau khổ', 'tủi thân', 'thất vọng', 'chán nản',
                'tuyệt vọng', 'tâm trạng', 'buồn bã', 'ảm đạm', 'u ám',
                # Extended
                'đau lòng', 'đau đớn', 'xót xa', 'tan nát', 'rạn nứt',
                'sụp đổ', 'gục ngã', 'khóc thầm', 'lệ rơi', 'nước mắt',
                'giọt lệ', 'buồn tênh', 'buồn thiu', 'buồn man mác', 'héo hon',
                'héo úa', 'tàn phai', 'lụi tàn', 'chết lặng', 'trống rỗng',
                'vô vọng', 'bất lực', 'bơ vơ', 'bẽ bàng', 'chua xót',
                'cay đắng', 'đắng cay', 'ngậm ngùi', 'thương tâm', 'ai oán',
                # Music phrases
                'nhớ nhung', 'tan vỡ giấc mơ', 'mưa rơi', 'cô đơn',
                'xa cách', 'chia tay', 'nỗi đau', 'khóc thầm', 'lạc lõng',
                'đêm dài', 'mưa buồn', 'gió lạnh', 'lá rụng', 'mùa đông',
                'phố vắng', 'đường khuya', 'đêm lạnh', 'mưa chiều', 'chiều tà',
                'đau thương', 'tan tác', 'tro tàn', 'giấc mơ tan',
                # Gen Z / loanwords
                'toxic', 'sad', 'blue', 'down', 'depressed', 'broken',
                # Regional: Southern
                'buồn ghê', 'đau quá trời', 'khổ ghê',
                # Regional: Central
                'buồn chi rứa', 'đau rứt',
            ],
            'love': [
                # Core love words
                'yêu', 'thương', 'yêu thương', 'yêu dấu', 'yêu em', 'anh yêu',
                'yêu anh', 'tình yêu', 'tình', 'mến', 'quý',
                'thích', 'say', 'say đắm', 'si tình', 'luyến', 'luyến ái',
                'si mê', 'đắm say', 'say mê', 'mê mẩn', 'mê say', 'thiết tha',
                'ngưỡng mộ', 'trìu mến', 'âu yếm', 'yêu kiều', 'mến thương',
                # Extended
                'tình cảm', 'tình thương', 'tình yêu thương', 'thương nhớ',
                'nhớ anh', 'nhớ em', 'yêu nhau', 'đôi ta', 'hôn', 'ôm',
                'nắm tay', 'bên nhau', 'bên anh', 'bên em', 'cùng nhau',
                'trái tim', 'con tim', 'rung động', 'xao xuyến', 'bồi hồi',
                'nồng nàn', 'đằm thắm', 'ngọt ngào', 'dịu êm', 'ấm áp',
                'che chở', 'bao bọc', 'vỗ về', 'chăm sóc', 'lo lắng',
                'thủy chung', 'chung thủy', 'son sắt', 'keo sơn', 'gắn bó',
                'hẹn ước', 'lời hứa', 'mãi mãi', 'vĩnh viễn', 'trọn đời',
                # Music phrases
                'đêm tình', 'câu hát tình', 'bài ca tình yêu', 'melody tình',
                'nhịp đập', 'trái tim yêu', 'hơi ấm', 'nụ hôn', 'ánh mắt',
                # Gen Z / loanwords
                'love', 'crush', 'bae', 'honey', 'darling', 'couple',
                # Regional
                'thương lắm', 'yêu ghê', 'mê quá trời',
            ],
            'angry': [
                # Core angry words
                'giận', 'tức', 'giận dữ', 'tức giận', 'nổi giận', 'phẫn nộ',
                'căm hận', 'oán hận', 'hận', 'thù', 'ghét', 'căm ghét',
                'căm thù', 'cay cú', 'bực', 'bực mình', 'bực bội', 'tức tối',
                'nóng giận', 'cáu', 'cáu giận', 'phát điên', 'điên loạn',
                # Extended
                'phẫn uất', 'căm phẫn', 'thù hận', 'trả thù', 'báo thù',
                'nổi loạn', 'chống đối', 'phản kháng', 'bùng nổ', 'giận sôi',
                'sục sôi', 'bốc lửa', 'cháy bỏng', 'điên tiết', 'cuồng nộ',
                'thịnh nộ', 'lôi đình', 'đùng đùng', 'quát', 'gào',
                'la hét', 'chửi', 'mắng', 'trách', 'oán trách',
                'phản bội', 'lừa dối', 'dối trá', 'bội bạc', 'vô tâm',
                # Music phrases
                'đốt cháy', 'phá vỡ', 'nghiền nát', 'đập tan',
                # Gen Z / loanwords  
                'hate', 'mad', 'furious', 'rage', 'pissed',
            ],
            'peaceful': [
                # Core peaceful words
                'bình yên', 'thanh thản', 'yên bình', 'thư giãn', 'tĩnh lặng',
                'êm đềm', 'an lành', 'an nhiên', 'thanh tịnh', 'trong trẻo',
                'dịu dàng', 'nhẹ nhàng', 'mềm mại', 'lặng lẽ', 'tĩnh tâm',
                'thảnh thơi', 'nhàn nhã', 'nhẹ nhõm', 'thư thái', 'tự tại',
                # Extended
                'an yên', 'bình an', 'tĩnh lặng', 'yên ả', 'yên tĩnh',
                'phẳng lặng', 'im lặng', 'lặng thinh', 'lặng im', 'ngơi nghỉ',
                'nghỉ ngơi', 'thong thả', 'từ tốn', 'ung dung', 'an nhàn',
                'vô ưu', 'vô lo', 'thảnh thơi', 'thanh nhàn', 'bình tĩnh',
                'trầm tĩnh', 'điềm đạm', 'ôn hòa', 'dung hòa', 'hài hòa',
                # Music phrases / nature
                'gió nhẹ', 'mây trôi', 'nắng sớm', 'sương mai', 'biển lặng',
                'sóng êm', 'trăng sáng', 'đêm thanh', 'chiều yên', 'hoàng hôn',
                # Gen Z / loanwords
                'chill', 'relax', 'zen', 'peace', 'calm', 'easy',
            ],
            'excited': [
                # Core excited words
                'phấn khích', 'hào hứng', 'náo nức', 'sôi động', 'sôi nổi',
                'nhiệt tình', 'hừng hực', 'bùng cháy', 'rực rỡ', 'bừng sáng',
                'cuồng nhiệt', 'say sưa', 'đam mê', 'khao khát', 'khát khao',
                'háo hức', 'nồng nhiệt', 'bừng bừng', 'rộn ràng', 'nhộn nhịp',
                # Extended
                'bùng nổ', 'cháy bỏng', 'sục sôi', 'hừng hực', 'rạo rực',
                'nóng bỏng', 'mãnh liệt', 'dữ dội', 'cuồng si', 'điên cuồng',
                'phát cuồng', 'adreneline', 'kịch tính', 'gay cấn', 'hấp dẫn',
                'nổ tung', 'bùng lên', 'thăng hoa', 'bay bổng', 'tung bay',
                'nhảy', 'múa', 'quẩy', 'lắc', 'nhún nhảy',
                # Music phrases
                'beat drop', 'đỉnh cao', 'bùng nổ', 'xoay vòng',
                # Gen Z / loanwords
                'hype', 'lit', 'fire', 'on fire', 'wild', 'crazy', 'insane',
                'party', 'turn up', 'lets go',
            ],
            'melancholic': [
                # Core melancholic words
                'sầu', 'u sầu', 'sầu thương', 'sầu muộn', 'mơ màng', 'mơ hồ',
                'lãng mạn', 'hoài niệm', 'hoài cổ', 'nhung nhớ', 'nặng lòng',
                'lưu luyến', 'nuối tiếc', 'tiếc nuối', 'thương nhớ', 'hoài mong',
                'mộng mơ', 'mơ ước', 'xa vắng', 'vắng vẻ', 'hiu quạnh',
                # Extended  
                'trầm mặc', 'trầm ngâm', 'tư lự', 'suy tư', 'chiêm nghiệm',
                'miên man', 'bâng khuâng', 'vấn vương', 'vấp vương', 'phiêu lãng',
                'lang thang', 'lênh đênh', 'trôi dạt', 'phiêu bạt', 'lưu lạc',
                'cô quạnh', 'trống vắng', 'hoang vắng', 'quạnh hiu', 'tiêu điều',
                'uất nghẹn', 'nghẹn ngào', 'thổn thức', 'rưng rưng', 'chạnh lòng',
                'xao lòng', 'động lòng', 'nao lòng', 'não lòng', 'rối bời',
                # Music phrases
                'mưa nhạt nhòa', 'chiều thu', 'lá vàng', 'con đường cũ',
                'quán cũ', 'phố xưa', 'ngày xưa', 'thuở ấy', 'năm tháng',
                'ký ức', 'hồi ức', 'dĩ vãng', 'quá khứ', 'ngày cũ',
                # Gen Z / loanwords
                'nostalgia', 'bittersweet', 'vibe buồn', 'deep',
            ],
            'longing': [
                # Core longing words
                'nhớ', 'nhung nhớ', 'nhớ nhung', 'mong', 'mong chờ', 'chờ đợi',
                'trông', 'trông mong', 'trông đợi', 'khắc khoải', 'day dứt',
                'thao thức', 'băn khoăn', 'trăn trở', 'ray rứt', 'dằn vặt',
                'nhớ mong', 'nôn nao', 'nao nao', 'nao lòng', 'đứng ngồi không yên',
                # Extended
                'chờ', 'đợi', 'ngóng', 'ngóng chờ', 'mong mỏi', 'mòn mỏi',
                'đau đáu', 'canh cánh', 'ám ảnh', 'bâng quơ', 'ngẩn ngơ',
                'thẫn thờ', 'ngơ ngẩn', 'luyến tiếc', 'nhớ thương', 'tương tư',
                'vương vấn', 'nhớ da diết', 'nhớ khôn nguôi', 'nhớ quay quắt',
                'xa nhớ', 'gần thương', 'người xa', 'phương xa', 'nơi xa',
                'xa xôi', 'cách trở', 'ngàn dặm', 'muôn trùng', 'biền biệt',
                # Music phrases
                'chờ ngày gặp', 'ngày trở về', 'hẹn ngày mai', 'bao giờ gặp lại',
                'khi nào gặp', 'thương nhớ ai', 'ai nhớ ai', 'người ơi',
                # Gen Z / loanwords
                'miss', 'missing you', 'waiting', 'distance',
            ],
            'hope': [
                # Core hope words
                'hi vọng', 'hy vọng', 'ước', 'mơ', 'ước mơ', 'mơ ước',
                'ước ao', 'ao ước', 'mong ước', 'khát vọng', 'hoài bão',
                'lý tưởng', 'kỳ vọng', 'tin tưởng', 'tin cậy', 'tin',
                'niềm tin', 'tương lai', 'mai sau', 'ngày mai', 'sáng tỏ',
                # Extended
                'kỳ diệu', 'phép mầu', 'phép lạ', 'cơ hội', 'may mắn',
                'vận may', 'bước ngoặt', 'thay đổi', 'đổi thay', 'hồi sinh',
                'tái sinh', 'đứng dậy', 'vươn lên', 'bước tiếp', 'tiến lên',
                'tiến bước', 'chiến thắng', 'vượt qua', 'kiên cường', 'mạnh mẽ',
                'dũng cảm', 'can đảm', 'bất khuất', 'kiên trì', 'nỗ lực',
                'cố gắng', 'phấn đấu', 'quyết tâm', 'nghị lực', 'ý chí',
                # Music phrases
                'ánh sáng', 'con đường', 'cánh cửa', 'chân trời', 'bình minh mới',
                'ngày mới bắt đầu', 'mở lối', 'cầu vồng', 'nắng mai',
                # Gen Z / loanwords
                'dream', 'believe', 'keep going', 'never give up', 'hope',
                'positive', 'motivation', 'inspiration',
            ],
            'nostalgia': [
                # New category for music-specific nostalgia
                'kỷ niệm', 'hồi ức', 'thuở xưa', 'ngày ấy', 'thuở ấy',
                'năm xưa', 'ngày xưa', 'thuở bé', 'tuổi thơ', 'trường cũ',
                'bạn cũ', 'tình cũ', 'người cũ', 'nơi cũ', 'con đường cũ',
                'phố cũ', 'quán quen', 'căn phòng cũ', 'bài hát cũ',
                'nhớ lại', 'nhìn lại', 'quay lại', 'trở lại', 'trở về',
                'giấc mơ xưa', 'mùi hương cũ', 'giọng nói quen', 'dáng người xưa',
                'hương vị', 'mảnh vỡ', 'tàn tích', 'dấu chân', 'dấu vết',
            ],
            'disgust': [
                # New category
                'ghê', 'kinh', 'ghê tởm', 'kinh tởm', 'ghê sợ', 'kinh hãi',
                'khinh', 'khinh bỉ', 'coi thường', 'chê bai', 'miệt thị',
                'phỉ nhổ', 'ghét bỏ', 'ruồng bỏ', 'chán ghét', 'chán ngán',
                'buồn nôn', 'rởm', 'giả tạo', 'đạo đức giả', 'lố bịch',
            ],
            'fear': [
                # New category
                'sợ', 'sợ hãi', 'hoảng sợ', 'kinh sợ', 'hãi hùng', 'khiếp sợ',
                'khủng khiếp', 'rùng rợn', 'ghê rợn', 'ớn lạnh', 'rùng mình',
                'lo sợ', 'lo lắng', 'lo âu', 'hồi hộp', 'bất an',
                'hoang mang', 'hoảng loạn', 'run rẩy', 'run sợ', 'chấn động',
                'bàng hoàng', 'sửng sốt', 'ngỡ ngàng', 'choáng váng', 'chới với',
            ],
            'surprise': [
                # New category
                'ngạc nhiên', 'bất ngờ', 'kinh ngạc', 'sửng sốt', 'ngỡ ngàng',
                'choáng', 'chưng hửng', 'sốc', 'không ngờ', 'ngoài dự đoán',
                'lạ lùng', 'kỳ lạ', 'hiếm thấy', 'kỳ diệu', 'thần kỳ',
                'wow', 'ô', 'ôi', 'trời ơi', 'chao ơi',
            ],
        }

        # Intensity modifiers (Vietnamese)
        self.intensifiers = [
            'rất', 'cực', 'quá', 'lắm', 'nhiều', 'vô cùng', 'cực kỳ',
            'hết sức', 'tuyệt đối', 'hoàn toàn', 'thật',
            'thật sự', 'thực sự', 'quá đỗi', 'khôn xiết', 'vô bờ',
            'siêu', 'mega', 'vãi', 'ghê', 'dã man', 'kinh khủng',
        ]

        # Negation words (Vietnamese)
        self.negations = [
            'không', 'chẳng', 'chả', 'không còn', 'chẳng còn',
            'không thể', 'đâu', 'chưa', 'chưa bao giờ', 'chưa từng',
            'đừng', 'hết', 'không hề', 'nào có', 'đâu có',
        ]

        # Adversative conjunctions — the emotion AFTER them is the resolved one
        # ("buồn NHƯNG hạnh phúc" → hạnh phúc dominates). Used for recency weighting.
        self.adversatives = ['nhưng', 'tuy nhiên', 'thế nhưng', 'song', ' mà ', ' lại ']

        # Valence polarity of each category — used to redirect a NEGATED emotion to
        # its opposite pole ("không buồn" → positive, not just dampened sad).
        self._pos_emotions = {'happy', 'love', 'excited', 'hope', 'peaceful'}
        self._neg_emotions = {'sad', 'angry', 'melancholic', 'longing', 'disgust', 'fear'}

    def analyze_lyrics(self, lyrics: str) -> Dict[str, float]:

        if not lyrics or pd.isna(lyrics):
            return {emotion: 0.0 for emotion in self.emotion_words.keys()}

        lyrics_lower = lyrics.lower()

        emotion_scores = defaultdict(float)

        # Per-OCCURRENCE scoring (fixes the old `count *= -0.8`, which produced negative
        # scores that corrupted normalisation). For each match we look at a short
        # preceding window for negation/intensifier, and apply adversative recency.
        for emotion, word_list in self.emotion_words.items():
            for word in word_list:
                if word not in lyrics_lower:      # fast guard — skip regex when absent
                    continue
                for m in re.finditer(r'(?<!\w)' + re.escape(word) + r'(?!\w)', lyrics_lower):
                    start = m.start()
                    # preceding context, confined to the SAME clause (don't let a negation
                    # from a prior clause leak across a comma/period: "không vui, buồn").
                    window = re.split(r'[,.;:!?\n]', lyrics_lower[max(0, start - 24):start])[-1]
                    w = 1.0
                    if any(intn in window for intn in self.intensifiers):
                        w *= 1.5
                    # Adversative recency: emotion after 'nhưng/mà/...' is the resolved one.
                    if any(adv in lyrics_lower[max(0, start - 40):start] for adv in self.adversatives):
                        w *= 1.4
                    if any(neg in window for neg in self.negations):
                        # Negation flips valence to the opposite pole (dampened), instead of
                        # adding a negative count: "không buồn" → positive, "không vui" → sad.
                        tgt = self._negate_target(emotion)
                        if tgt is not None:
                            emotion_scores[tgt] += 0.7 * w
                        # neutral emotions (nostalgia/surprise) negated → dropped
                    else:
                        emotion_scores[emotion] += w

        # Normalize scores (all non-negative now)
        total = sum(emotion_scores.values())
        if total > 0:
            emotion_scores = {k: v / total for k, v in emotion_scores.items()}
        else:
            emotion_scores = {emotion: 0.0 for emotion in self.emotion_words.keys()}

        return dict(emotion_scores)

    def _negate_target(self, emotion: str) -> 'str | None':
        """Opposite-polarity category a negated emotion should count toward."""
        if emotion in self._pos_emotions:
            return 'sad'
        if emotion in self._neg_emotions:
            return 'happy'
        return None


class EmotionClassifier:

    def __init__(self, model_name: str = None):
        """Initialize emotion classifier with PhoBERT.
        Uses config.PHOBERT_MODEL by default (vinai/phobert-base-v2).
        """
        if model_name is None:
            try:
                import config as app_config
                model_name = app_config.PHOBERT_MODEL
            except ImportError:
                model_name = 'vinai/phobert-base-v2'
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

        try:
            self.model = AutoModel.from_pretrained(model_name)
            self.tokenizer = AutoTokenizer.from_pretrained(model_name)
            self.model.to(self.device)
            self.model.eval()
            self.available = True
        except Exception as e:
            logger.warning("Could not load PhoBERT model: %s", e)
            self.available = False

        # Emotion dimension mapping (based on Russell's Circumplex Model)
        self.emotion_dimensions = {
            'happy': (0.8, 0.6),      # High valence, moderate arousal
            'sad': (0.2, 0.3),         # Low valence, low arousal
            'love': (0.7, 0.5),        # High valence, moderate arousal
            'angry': (0.3, 0.8),       # Low valence, high arousal
            'peaceful': (0.6, 0.2),    # Moderate-high valence, low arousal
            'excited': (0.8, 0.9),     # High valence, high arousal
            'melancholic': (0.35, 0.4), # Low-moderate valence, low-moderate arousal
            'longing': (0.4, 0.5),     # Low-moderate valence, moderate arousal
            'hope': (0.7, 0.6),        # High valence, moderate-high arousal
            'nostalgia': (0.4, 0.35),  # Low-moderate valence, low-moderate arousal
            'disgust': (0.2, 0.6),     # Low valence, moderate-high arousal
            'fear': (0.2, 0.7),        # Low valence, high arousal
            'surprise': (0.6, 0.8),    # Moderate valence, high arousal
        }

    def encode_lyrics(self, lyrics: str, max_length: int = 256) -> Optional[np.ndarray]:
        """
        Encode lyrics using PhoBERT with attention pooling

        Args:
            lyrics: Vietnamese lyrics text
            max_length: Maximum sequence length (PhoBERT-base position limit is 258;
                        capped at 256 — 512 previously could overflow/clip — V17 fix B1)

        Returns:
            Embedding vector or None if failed
        """
        if not self.available or not lyrics or pd.isna(lyrics):
            return None

        try:
            # Vietnamese word segmentation required by PhoBERT
            segmented_lyrics = ViTokenizer.tokenize(str(lyrics))
            
            # Tokenize
            inputs = self.tokenizer(
                segmented_lyrics,
                return_tensors='pt',
                padding=True,
                truncation=True,
                max_length=max_length
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            # Get embeddings
            with torch.no_grad():
                outputs = self.model(**inputs)

                # Use attention pooling instead of just CLS token
                # This captures more semantic information from the entire lyrics
                hidden_states = outputs.last_hidden_state  # (batch, seq_len, hidden_dim)
                attention_mask = inputs['attention_mask'].unsqueeze(-1)  # (batch, seq_len, 1)

                # Weighted average by attention mask
                embeddings = (hidden_states * attention_mask).sum(1) / attention_mask.sum(1)
                embeddings = embeddings.cpu().numpy()[0]

            return embeddings

        except Exception as e:
            logger.warning("Error encoding lyrics: %s", e)
            return None

    def emotions_to_valence_arousal(self, emotion_scores: Dict[str, float]) -> Tuple[float, float]:

        valence = 0.5
        arousal = 0.5
        total_weight = 0.0

        for emotion, score in emotion_scores.items():
            if emotion in self.emotion_dimensions and score > 0:
                v, a = self.emotion_dimensions[emotion]
                valence += v * score
                arousal += a * score
                total_weight += score

        if total_weight > 0:
            valence /= (1 + total_weight)
            arousal /= (1 + total_weight)

        return (np.clip(valence, 0, 1), np.clip(arousal, 0, 1))


class MultimodalEmotionFusion:

    def __init__(self, audio_weight: float = 0.5, lyrics_weight: float = 0.5):

        self.audio_weight = audio_weight
        self.lyrics_weight = lyrics_weight

        # Normalize weights
        total = audio_weight + lyrics_weight
        if total > 0:
            self.audio_weight /= total
            self.lyrics_weight /= total

    def fuse_emotions(self,
                     audio_valence: float,
                     audio_energy: float,
                     lyrics_valence: float,
                     lyrics_arousal: float,
                     audio_confidence: float = 1.0,
                     lyrics_confidence: float = 1.0) -> Tuple[float, float]:

        # Adaptive weighting based on confidence
        audio_w = self.audio_weight * audio_confidence
        lyrics_w = self.lyrics_weight * lyrics_confidence

        total_w = audio_w + lyrics_w
        if total_w > 0:
            audio_w /= total_w
            lyrics_w /= total_w
        else:
            audio_w = 0.5
            lyrics_w = 0.5

        # Fuse valence and energy/arousal
        final_valence = audio_w * audio_valence + lyrics_w * lyrics_valence
        final_energy = audio_w * audio_energy + lyrics_w * lyrics_arousal

        return (np.clip(final_valence, 0, 1), np.clip(final_energy, 0, 1))

    def get_emotion_label(self, valence: float, energy: float) -> str:

        # Quadrant-based classification
        if valence >= 0.5 and energy >= 0.5:
            # Q1: Happy/Excited
            if valence > 0.7 and energy > 0.7:
                return 'excited'
            else:
                return 'happy'
        elif valence < 0.5 and energy >= 0.5:
            # Q2: Tense/Angry. "angry" only for genuinely extreme negative+high-energy;
            # most low-valence high-arousal songs are intense/dramatic ("tense"), not
            # angry (angry music is rare in V-pop) — avoids over-labelling sad-intense
            # ballads as angry.
            if valence < 0.30 and energy > 0.68:
                return 'angry'
            else:
                return 'tense'
        elif valence < 0.5 and energy < 0.5:
            # Q3: Sad/Depressed
            if valence < 0.3:
                return 'sad'
            else:
                return 'melancholic'
        else:
            # Q4: Calm/Peaceful
            if energy < 0.3:
                return 'peaceful'
            else:
                return 'calm'


# Singleton instances
_emotion_lexicon = None
_emotion_classifier = None
_emotion_fusion = None

def get_emotion_analyzer():
    """Get singleton instance of emotion analysis components"""
    global _emotion_lexicon, _emotion_classifier, _emotion_fusion

    if _emotion_lexicon is None:
        _emotion_lexicon = VietnameseEmotionLexicon()

    if _emotion_classifier is None:
        _emotion_classifier = EmotionClassifier()

    if _emotion_fusion is None:
        _emotion_fusion = MultimodalEmotionFusion(audio_weight=0.5, lyrics_weight=0.5)

    return _emotion_lexicon, _emotion_classifier, _emotion_fusion


if __name__ == "__main__":
    # Test emotion analysis
    print("=" * 80)
    print("🎭 EMOTION ANALYSIS MODULE - TEST")
    print("=" * 80)

    lexicon, classifier, fusion = get_emotion_analyzer()

    # Test Vietnamese lyrics
    test_lyrics = [
        "Anh yêu em nhiều lắm, em làm anh vui sướng và hạnh phúc",
        "Buồn lắm người ơi, lòng anh đau khổ vì xa em",
        "Giận lắm rồi, tức quá đi, anh không thể chịu được nữa",
        "Bình yên trong lòng, thanh thản nhẹ nhàng như gió"
    ]

    print("\n📝 Testing Lexicon-based Analysis:")
    for lyrics in test_lyrics:
        scores = lexicon.analyze_lyrics(lyrics)
        valence, arousal = classifier.emotions_to_valence_arousal(scores)
        label = fusion.get_emotion_label(valence, arousal)

        print(f"\nLyrics: {lyrics[:50]}...")
        print(f"Emotions: {sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]}")
        print(f"Valence: {valence:.2f}, Arousal: {arousal:.2f} → {label}")

    print("\n✅ Emotion analysis test completed!")

