# -*- coding: utf-8 -*-

from uuid import uuid4

from tornado.gen import Return, coroutine

from tornadoes import ESConnection
from tornado import escape
from tornado.testing import AsyncTestCase, gen_test
from tornado.ioloop import IOLoop
from mock import Mock


class ESConnectionTestBase(AsyncTestCase):

    def setUp(self):
        super(ESConnectionTestBase, self).setUp()
        self.es_connection = ESConnection("localhost", "9200", self.io_loop)
        self._set_version()

    def tearDown(self):
        if not IOLoop.initialized() or self.io_loop is not IOLoop.instance():
            self.io_loop.close(all_fds=True)
        super(AsyncTestCase, self).tearDown()

    def _set_version(self):
        self.es_connection.get_by_path("/", self.stop)
        response = self.wait()
        response = escape.json_decode(response.body)
        version = response['version']['number']
        self.version = [int(n) for n in version.split('.') if n.isdigit()]

    def _set_count_query(self, query):
        if self.version[0] < 1:
            return query['query']
        return query


class TestESConnection(ESConnectionTestBase):
    @coroutine
    def _make_multisearch(self):
        body = {"query": {"term": {"_id": "171171"}}}
        self.es_connection.multi_search(index="teste", body=body)
        body = {"query": {"term": {"_id": "101010"}}}
        self.es_connection.multi_search(index="neverEndIndex", body=body)

        response = yield self.es_connection.apply_search()
        raise Return(response)

    def _verify_response_and_returns_dict(self, response):
        self.assertTrue(response.code in [200, 201], "Wrong response code: %d." % response.code)
        response = escape.json_decode(response.body)
        return response

    @gen_test
    def test_simple_search(self):
        response = yield self.es_connection.get_by_path("/_search?q=_id:http\:\/\/localhost\/noticia\/2\/fast")
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["hits"]["total"], 1)
        self.assertEqual(response["hits"]["hits"][0]["_id"], u'http://localhost/noticia/2/fast')

    @gen_test
    def test_search_for_specific_type_with_query(self):
        response = yield self.es_connection.search(body={"query": {"term": {"ID": "171171"}}}, doc_type="materia",
                                                   index="teste")

        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["hits"]["total"], 1)
        self.assertEqual(response["hits"]["hits"][0]["_id"], u'171171')

    @gen_test
    def test_search_specific_index(self):
        response = yield self.es_connection.search(index="outroteste")
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["hits"]["total"], 14)

    @gen_test
    def test_search_apecific_type(self):
        response = yield self.es_connection.search(doc_type='galeria')
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["hits"]["total"], 2)

    @gen_test
    def test_should_access_specific_document(self):
        response = yield self.es_connection.get(index="teste", doc_type="materia", doc_id="171171")
        source = response["_source"]
        self.assertEqual(source['Portal'], "G1")
        self.assertEqual(source['Macrotema'], "Noticias")

    def test_should_accumulate_searches_before_search(self):
        body = {"query": {"term": {"_id": "171171"}}}
        self.es_connection.multi_search("teste", body=body)
        body = {"query": {"term": {"body": "multisearch"}}}
        self.es_connection.multi_search("neverEndIndex", body=body)

        self.assertListEqual(['{"index": "teste"}\n{"query": {"term": {"_id": "171171"}}}',
                              '{"index": "neverEndIndex"}\n{"query": {"term": {"body": "multisearch"}}}'
                              ], self.es_connection.bulk.bulk_list)

    def test_should_generate_empty_header_with_no_index_specified(self):
        body = {"query": {"term": {"_id": "171171"}}}
        self.es_connection.multi_search(index=None, body=body)
        body = {"query": {"term": {"body": "multisearch"}}}
        self.es_connection.multi_search(index=None, body=body)

        self.assertListEqual(['{}\n{"query": {"term": {"_id": "171171"}}}',
                              '{}\n{"query": {"term": {"body": "multisearch"}}}'
                              ], self.es_connection.bulk.bulk_list)

    @gen_test
    def test_should_make_two_searches(self):
        response = yield self._make_multisearch()
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response['responses'][0]['hits']['hits'][0]['_id'], "171171")
        self.assertFalse("hits" in response['responses'][1])

    @gen_test
    def test_should_clean_search_list_after_search(self):
        yield self._make_multisearch()
        self.assertListEqual([], self.es_connection.bulk.bulk_list)

    def test_can_put_and_delete_document(self):
        try:
            doc_id = str(uuid4())

            self.es_connection.put("test", "document", doc_id, {
                "test": "document",
                "other": "property"
            }, parameters={'refresh': True}, callback=self.stop)

            response = self.wait()
            response_dict = self._verify_response_and_returns_dict(response)
            self.assertEqual(response_dict['_index'], 'test')
            self.assertEqual(response_dict['_type'], 'document')
            self.assertEqual(response_dict['_id'], doc_id)
            self.assertIn('refresh=True', response.request.url)
        finally:
            self.es_connection.delete("test", "document", doc_id,
                                      parameters={'refresh': True}, callback=self.stop)
            response = self._verify_response_and_returns_dict(response)

            self.assertTrue(response['found'])
            self.assertEqual(response['_index'], 'test')
            self.assertEqual(response['_type'], 'document')
            self.assertEqual(response['_id'], doc_id)

    def test_update_partial_document(self):
        uid = escape.url_escape("http://localhost/noticia/5/fast")
        self.es_connection.update(index='teste',
                                  type='materia',
                                  uid=uid,
                                  contents={"Tags": "nova"},
                                  callback=self.stop)

        response = self._verify_response_and_returns_dict(response)

        self.assertEqual(response["_index"], 'teste')
        self.assertEqual(response["_version"], 2)

    def test_count_specific_index(self):
        self.es_connection.count(callback=self.stop, index="outroteste")
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["count"], 14)

    def test_count_specific_type(self):
        self.es_connection.count(callback=self.stop, type='galeria')
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["count"], 2)

    def test_count_specific_query(self):
        source = {"query": {"term": {"_id": "171171"}}}
        source = self._set_count_query(source)
        self.es_connection.count(callback=self.stop, source=source)
        response = self._verify_response_and_returns_dict(response)
        self.assertEqual(response["count"], 1)

    def test_count_specific_query_with_parameters(self):
        source = {"query": {"term": {"_id": "171171"}}}
        source = self._set_count_query(source)
        parameters = {'refresh': True}
        self.es_connection.count(callback=self.stop, source=source, parameters=parameters)
        response = self.wait()
        response_dict = self._verify_response_and_returns_dict(response)
        self.assertEqual(response_dict["count"], 1)
        self.assertTrue(response.request.url.endswith('_count?refresh=True'))

    def test_count_specific_query_with_many_parameters(self):
        source = {"query": {"term": {"_id": "171171"}}}
        source = self._set_count_query(source)
        parameters = {'df': '_id', 'test': True}
        self.es_connection.count(callback=self.stop, source=source, parameters=parameters)
        response = self.wait()
        response_dict = self._verify_response_and_returns_dict(response)
        self.assertEqual(response_dict["count"], 1)
        self.assertTrue('df=_id' in response.request.url)
        self.assertTrue('test=True' in response.request.url)


class TestESConnectionWithTornadoGen(ESConnectionTestBase):

    @gen_test
    def test_simple_search(self):
        response = yield self.es_connection.get_by_path("/_search?q=_id:http\:\/\/localhost\/noticia\/2\/fast", self.stop)

        response = self._verify_status_code_and_return_response(response)

        self.assertEqual(response["hits"]["total"], 1)
        self.assertEqual(response["hits"]["hits"][0]["_id"], u'http://localhost/noticia/2/fast')

    @gen_test
    def test_search_for_specific_type_with_query(self):
        response = yield self.es_connection.search(
            source={"query": {"term": {"ID": "171171"}}},
            type="materia", index="teste"
        )

        response = self._verify_status_code_and_return_response(response)
        self.assertEqual(response["hits"]["total"], 1)
        self.assertEqual(response["hits"]["hits"][0]["_id"], u'171171')

    @gen_test
    def test_search_specific_index(self):
        response = yield self.es_connection.search(index="outroteste")
        response = self._verify_status_code_and_return_response(response)
        self.assertEqual(response["hits"]["total"], 14)

    @gen_test
    def test_search_apecific_type(self):
        response = yield self.es_connection.search(type='galeria')
        response = self._verify_status_code_and_return_response(response)
        self.assertEqual(response["hits"]["total"], 2)

    @gen_test
    def test_should_access_specific_document_using_tornado_gen(self):
        response = yield self.es_connection.get(index="teste", type="materia", uid="171171")
        response = response["_source"]
        self.assertEqual(response['Portal'], "G1")
        self.assertEqual(response['Macrotema'], "Noticias")

    @gen_test
    def test_should_make_two_searches(self):
        self._make_multisearch()
        response = yield self.es_connection.apply_search()
        response = self._verify_status_code_and_return_response(response)

        self.assertEqual(response['responses'][0]['hits']['hits'][0]['_id'], "171171")
        self.assertFalse("hits" in response['responses'][1])

    @gen_test
    def test_should_clean_search_list_after_search(self):
        self._make_multisearch()
        response = yield self.es_connection.apply_search()
        response = self._verify_status_code_and_return_response(response)

        self.assertListEqual([], self.es_connection.bulk.bulk_list)

    @gen_test
    def test_can_put_and_delete_document(self):
        try:
            doc_id = str(uuid4())

            response = yield self.es_connection.put("test", "document", doc_id, {
                "test": "document",
                "other": "property"
            }, parameters={'refresh': True})

            response_dict = self._verify_status_code_and_return_response(response)
            self.assertEqual(response_dict['_index'], 'test')
            self.assertEqual(response_dict['_type'], 'document')
            self.assertEqual(response_dict['_id'], doc_id)
            self.assertIn('refresh=True', response.request.url)
        finally:
            response = yield self.es_connection.delete("test", "document", doc_id,
                                                       parameters={'refresh': True})
            response = self._verify_status_code_and_return_response(response)

            self.assertTrue(response['found'])
            self.assertEqual(response['_index'], 'test')
            self.assertEqual(response['_type'], 'document')
            self.assertEqual(response['_id'], doc_id)

    @gen_test
    def test_count_specific_index(self):
        response = yield self.es_connection.count(index="outroteste")
        self.assertCount(response, 14)

    @gen_test
    def test_count_specific_type(self):
        response = yield self.es_connection.count(type='galeria')
        self.assertCount(response, 2)

    @gen_test
    def test_count_specific_query(self):
        source = {"query": {"term": {"_id": "171171"}}}
        source = self._set_count_query(source)
        response = yield self.es_connection.count(source=source)
        self.assertCount(response, 1)

    @gen_test
    def test_count_specific_query_with_parameters(self):
        source = {"query": {"term": {"_id": "171171"}}}
        source = self._set_count_query(source)
        parameters = {'refresh': True}
        response = yield self.es_connection.count(callback=self.stop, source=source, parameters=parameters)
        self.assertCount(response, 1)
        self.assertTrue(response.request.url.endswith('_count?refresh=True'))

    @gen_test
    def test_use_of_custom_http_clients(self):
        mocked_http_client = Mock()
        mocked_http_client.fetch = Mock()

        es_connection = ESConnection("localhost",
                                     "9200",
                                     self.io_loop,
                                     custom_client=mocked_http_client)

        es_connection.search(callback=self.stop,
                             source={"query": {"term": {"ID": "171171"}}},
                             type="materia", index="teste")

        mocked_http_client.fetch.assert_called()

    @gen_test
    def test_initilize_client_from_uri(self):
        es_connection = ESConnection.from_uri("https://dummy.server:1234/")
        self.assertEqual(es_connection.url, "https://dummy.server:1234")

    @gen_test
    def test_initilize_client_from_invalid_uri(self):
        with self.assertRaises(ValueError):
            ESConnection.from_uri("<<invalid:1234uri/")

    def assertCount(self, response, count):
        response_dict = self._verify_status_code_and_return_response(response)
        self.assertEqual(response_dict["count"], count)

    def _make_multisearch(self):
        source = {"query": {"term": {"_id": "171171"}}}
        self.es_connection.multi_search(index="teste", source=source)
        source = {"query": {"term": {"_id": "101010"}}}
        self.es_connection.multi_search(index="neverEndIndex", source=source)

    def _verify_status_code_and_return_response(self, response):
        self.assertTrue(response.code in [200, 201], "Wrong response code: %d." % response.code)
        response = escape.json_decode(response.body)
        return response