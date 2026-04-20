from abc import ABC, abstractmethod

class RssCrawler(ABC):
    @abstractmethod
    def find(self, url: str):
        pass
    
