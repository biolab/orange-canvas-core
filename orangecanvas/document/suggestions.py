import os
import pickle
from collections import defaultdict

from .. import config
from .interactions import NewLinkAction


class Suggestions:
    def __init__(self):
        self.__frequencies_path = config.data_dir() + "/widget-use-frequency.p"

        self.__scheme = None
        self.__last_direction = None
        self.link_frequencies = defaultdict(int)
        self.source_probability = defaultdict(lambda: defaultdict(float))
        self.sink_probability = defaultdict(lambda: defaultdict(float))

        if not self.load_link_frequency():
            self.default_link_frequency()

    def load_link_frequency(self):
        if not os.path.isfile(self.__frequencies_path):
            return False
        file = open(self.__frequencies_path, "rb")
        self.link_frequencies = pickle.load(file)

        self.overwrite_probabilities_with_frequencies()
        return True

    def default_link_frequency(self):
        self.link_frequencies[("File", "Data Table", NewLinkAction.FROM_SOURCE)] = 3
        self.overwrite_probabilities_with_frequencies()

    def overwrite_probabilities_with_frequencies(self):
        for link, count in self.link_frequencies.items():
            self.increment_probability(link[0], link[1], link[2], count)

    def write_link_frequency(self):
        pickle.dump(self.link_frequencies, open(self.__frequencies_path, "wb"))

    def new_link(self, link):
        source_id = link.source_node.description.name
        sink_id = link.sink_node.description.name

        link_key = (source_id, sink_id, self.__last_direction)
        self.link_frequencies[link_key] += 1

        self.increment_probability(source_id, sink_id, self.__last_direction, 1)

        self.write_link_frequency()

    def increment_probability(self, source_id, sink_id, direction, factor):
        if direction == NewLinkAction.FROM_SOURCE:
            self.source_probability[source_id][sink_id] += factor
            self.sink_probability[sink_id][source_id] += factor * 0.5
        else:  # FROM_SINK
            self.source_probability[source_id][sink_id] += factor * 0.5
            self.sink_probability[sink_id][source_id] += factor

    def get_sink_suggestions(self, source_id):
        return self.source_probability[source_id]

    def get_source_suggestions(self, sink_id):
        return self.sink_probability[sink_id]

    def set_scheme(self, scheme):
        self.__scheme = scheme
        scheme.onNewLink(self.new_link)

    def set_last_direction(self, direction):
        """
        When opening quick menu, before the widget is created, set the direction
        of creation (FROM_SINK, FROM_SOURCE).
        """
        self.__last_direction = direction
