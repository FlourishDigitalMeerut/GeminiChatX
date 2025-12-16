from sqlmodel import Session, select # pyright: ignore[reportMissingImports]
from models.database import engine

class BaseManager:
    def __init__(self, model_class, instance_class):
        self.model_class = model_class
        self.instance_class = instance_class
        self._instances = {}
        self._load_existing_instances()

    def _load_existing_instances(self):
        with Session(engine) as s:
            for m in s.exec(select(self.model_class)).all():
                self._instances[m.id] = self.instance_class(m)

    def get(self, bot_id: int):
        return self._instances.get(bot_id)

    def create(self, **kwargs):
        with Session(engine) as s:
            m = self.model_class(**kwargs)
            s.add(m)
            s.commit()
            s.refresh(m)
        self._instances[m.id] = self.instance_class(m)
        return m