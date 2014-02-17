# -*- coding: utf-8 -*-

"""
Copyright (C) 2014 Dariusz Suchojad <dsuch at zato.io>

Licensed under LGPLv3, see LICENSE.txt for terms and conditions.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

# stdlib
from contextlib import closing
from traceback import format_exc

# Zato
from zato.common.broker_message import PUB_SUB_TOPIC
from zato.common.odb.model import Cluster, PubSubTopic
from zato.common.odb.query import topic_list
from zato.server.service import Int
from zato.server.service.internal import AdminService, AdminSIO

# ################################################################################################################################

class GetList(AdminService):
    """ Returns a list of topics available.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_pubsub_topics_get_list_request'
        response_elem = 'zato_pubsub_topics_get_list_response'
        input_required = ('cluster_id',)
        output_required = ('id', 'name', 'is_active', Int('current_depth'), Int('max_depth'),
            Int('consumers_count'), Int('producers_count'))

    def get_data(self, session):
        for item in topic_list(session, self.request.input.cluster_id, False):
            item.current_depth = self.pubsub.get_topic_depth(item.name)
            item.consumers_count = self.pubsub.get_consumers_count(item.name)
            item.producers_count = self.pubsub.get_producers_count(item.name)
            yield item

    def handle(self):
        with closing(self.odb.session()) as session:
            self.response.payload[:] = self.get_data(session)

# ################################################################################################################################

class Create(AdminService):
    """ Creates a new topic.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_pubsub_topics_create_request'
        response_elem = 'zato_pubsub_topics_create_response'
        input_required = ('cluster_id', 'name', 'is_active', 'max_depth')
        output_required = ('id', 'name')

    def handle(self):
        input = self.request.input

        with closing(self.odb.session()) as session:
            try:
                cluster = session.query(Cluster).filter_by(id=input.cluster_id).first()

                # Let's see if we already have a topic of that name before committing
                # any stuff into the database.
                existing_one = session.query(PubSubTopic).\
                    filter(Cluster.id==input.cluster_id).\
                    filter(PubSubTopic.name==input.name).first()

                if existing_one:
                    raise Exception('Topic `{}` already exists on this cluster'.format(input.name))

                topic = PubSubTopic(None, input.name, input.is_active, input.max_depth, cluster.id)

                session.add(topic)
                session.commit()

            except Exception, e:
                msg = 'Could not create a topic, e:`{}`'.format(format_exc(e))
                self.logger.error(msg)
                session.rollback()

                raise 
            else:
                input.action = PUB_SUB_TOPIC.CREATE
                input.sec_type = 'basic_topic'
                self.broker_client.publish(input)

            self.response.payload.id = topic.id
            self.response.payload.name = topic.name

# ################################################################################################################################

class Edit(AdminService):
    """ Updates a topic.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_pubsub_topics_edit_request'
        response_elem = 'zato_pubsub_topics_edit_response'
        input_required = ('id', 'cluster_id', 'name', 'is_active', 'max_depth')
        output_required = ('id', 'name')

    def handle(self):
        input = self.request.input
        with closing(self.odb.session()) as session:
            try:
                existing_one = session.query(PubSubTopic).\
                    filter(Cluster.id==input.cluster_id).\
                    filter(PubSubTopic.name==input.name).\
                    filter(PubSubTopic.id!=input.id).\
                    first()

                if existing_one:
                    raise Exception('Topic `{}` already exists on this cluster'.format(input.name))

                topic = session.query(PubSubTopic).filter_by(id=input.id).one()
                old_name = topic.name

                topic.name = input.name
                topic.is_active = input.is_active
                topic.max_depth = input.max_depth

                session.add(topic)
                session.commit()

            except Exception, e:
                msg = 'Could not update the topic, e:`{}'.format(format_exc(e))
                self.logger.error(msg)
                session.rollback()

                raise 
            else:
                input.action = PUB_SUB_TOPIC.EDIT
                input.old_name = old_name
                self.broker_client.publish(input)

                self.response.payload.id = topic.id
                self.response.payload.name = topic.name

# ################################################################################################################################

class Delete(AdminService):
    """ Deletes a topic.
    """
    class SimpleIO(AdminSIO):
        request_elem = 'zato_pubsub_topics_delete_request'
        response_elem = 'zato_pubsub_topics_delete_response'
        input_required = ('id',)

    def handle(self):
        with closing(self.odb.session()) as session:
            try:
                topic = session.query(PubSubTopic).\
                    filter(PubSubTopic.id==self.request.input.id).\
                    one()

                session.delete(topic)
                session.commit()
            except Exception, e:
                msg = 'Could not delete the topic, e:`{}`'.format(format_exc(e))
                self.logger.error(msg)
                session.rollback()

                raise
            else:
                self.request.input.action = PUB_SUB_TOPIC.DELETE
                self.request.input.name = topic.name
                self.broker_client.publish(self.request.input)

# ################################################################################################################################