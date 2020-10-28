import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from Crypto.Random import get_random_bytes
from gmssl import sm2

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class GMSM2Crypto:
    def __init__(self, public_key, private_key):
        self.sm2_crypt = sm2.CryptSM2(
            public_key=public_key, private_key=private_key
        )

    def encrypt(self, text):
        return base64.urlsafe_b64encode(
            self.sm2_crypt.encrypt(bytes(text, encoding='utf8'))
        ).decode('utf8')

    def decrypt(self, text):
        return self.sm2_crypt.decrypt(
            base64.urlsafe_b64decode(bytes(text, encoding='utf8'))
        ).decode('utf8')


class AESCrypto:
    """
    AES
    除了MODE_SIV模式key长度为：32, 48, or 64,
    其余key长度为16, 24 or 32
    详细见AES内部文档
    CBC模式传入iv参数
    本例使用常用的ECB模式
    """

    def __init__(self, key):
        if len(key) > 32:
            key = key[:32]
        self.key = self.to_16(key)

    @staticmethod
    def to_16(key):
        """
        转为16倍数的bytes数据
        :param key:
        :return:
        """
        key = bytes(key, encoding="utf8")
        while len(key) % 16 != 0:
            key += b'\0'
        return key  # 返回bytes

    def aes(self):
        return AES.new(self.key, AES.MODE_ECB)  # 初始化加密器

    def encrypt(self, text):
        aes = self.aes()
        return str(base64.encodebytes(aes.encrypt(self.to_16(text))),
                   encoding='utf8').replace('\n', '')  # 加密

    def decrypt(self, text):
        aes = self.aes()
        return str(aes.decrypt(base64.decodebytes(bytes(text, encoding='utf8'))).rstrip(b'\0').decode("utf8"))  # 解密


class AESCryptoGCM:
    """
    使用AES GCM模式
    """

    def __init__(self, key):
        self.key = self.process_key(key)

    @staticmethod
    def process_key(key):
        """
        返回32 bytes 的key
        """
        if not isinstance(key, bytes):
            key = bytes(key, encoding='utf-8')

        if len(key) >= 32:
            return key[:32]

        return pad(key, 32)

    def encrypt(self, text):
        """
        加密text，并将 header, nonce, tag (3*16 bytes, base64后变为 3*24 bytes)
        附在密文前。解密时要用到。
        """
        header = get_random_bytes(16)
        cipher = AES.new(self.key, AES.MODE_GCM)
        cipher.update(header)
        ciphertext, tag = cipher.encrypt_and_digest(bytes(text, encoding='utf-8'))

        result = []
        for byte_data in (header, cipher.nonce, tag, ciphertext):
            result.append(base64.b64encode(byte_data).decode('utf-8'))

        return ''.join(result)

    def decrypt(self, text):
        """
        提取header, nonce, tag并解密text。
        """
        metadata = text[:72]
        header = base64.b64decode(metadata[:24])
        nonce = base64.b64decode(metadata[24:48])
        tag = base64.b64decode(metadata[48:])
        ciphertext = base64.b64decode(text[72:])

        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)

        cipher.update(header)
        plain_text_bytes = cipher.decrypt_and_verify(ciphertext, tag)
        return plain_text_bytes.decode('utf-8')


def get_aes_crypto(key=None, mode='GCM'):
    if key is None:
        key = settings.SECRET_KEY
    if mode == 'ECB':
        a = AESCrypto(key)
    elif mode == 'GCM':
        a = AESCryptoGCM(key)
    return a


def get_gm_sm2_crypto():
    return GMSM2Crypto(
        public_key=settings.SECURITY_CRYPTO_GM_SM2_PUBLIC_KEY,
        private_key=settings.SECURITY_CRYPTO_GM_SM2_PRIVATE_KEY
    )


aes_ecb_crypto = get_aes_crypto(mode='ECB')
aes_crypto = get_aes_crypto(mode='GCM')
gm_sm2_crypto = get_gm_sm2_crypto()


class Crypto:
    methods = {
        'aes_ecb': aes_ecb_crypto,
        'aes': aes_crypto,
        'gm_sm2': gm_sm2_crypto
    }

    def __init__(self):
        methods = self.__class__.methods.copy()
        method = methods.pop(settings.SECURITY_DATA_CRYPTO_METHOD, None)
        if method is None:
            raise ImproperlyConfigured(
                f'{settings.SECURITY_DATA_CRYPTO_METHOD} crypto method not supported'
            )
        self.methods = [method, *methods.values()]

    @property
    def encryptor(self):
        return self.methods[0]

    def encrypt(self, text):
        return self.encryptor.encrypt(text)

    def decrypt(self, text):
        for decryptor in self.methods:
            try:
                return decryptor.decrypt(text)
            except (TypeError, ValueError, UnicodeDecodeError):
                continue


crypto = Crypto()
