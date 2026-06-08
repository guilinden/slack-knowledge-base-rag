angular.module('knowledgeBase', ['ngSanitize'])

  .filter('markdown', ['$sce', function ($sce) {
    return function (text) {
      if (!text) return '';
      return $sce.trustAsHtml(marked.parse(text));
    };
  }])

  .controller('ChatController', ['$http', '$scope', '$timeout', function ($http, $scope, $timeout) {
    $scope.messages   = [];
    $scope.question   = '';
    $scope.loading    = false;
    $scope.topic      = '';
    $scope.topK       = 3;
    $scope.repos      = [];
    $scope.sidebarOpen = false;

    // Load registered repos for the sidebar
    function loadRepos() {
      $http.get('/api/repos/').then(function (resp) {
        $scope.repos = resp.data;
      }).catch(angular.noop);
    }
    loadRepos();

    $scope.send = function () {
      var q = ($scope.question || '').trim();
      if (!q || $scope.loading) return;

      $scope.messages.push({ role: 'user', text: q, timestamp: new Date() });
      $scope.question = '';
      $scope.loading  = true;
      _scrollToBottom();

      $http.post('/api/chat/query', {
        question : q,
        user     : 'ui-user',
        top_k    : parseInt($scope.topK, 10),
        topic    : $scope.topic || null
      }).then(function (resp) {
        $scope.messages.push({
          role       : 'assistant',
          type       : resp.data.type,
          data       : resp.data,
          timestamp  : new Date(),
          showSources: false,
          showRepos  : false
        });
      }).catch(function (err) {
        var detail = err.data && err.data.detail
          ? err.data.detail
          : 'Request failed. Is the service running?';
        $scope.messages.push({ role: 'error', text: detail, timestamp: new Date() });
      }).finally(function () {
        $scope.loading = false;
        $timeout(_scrollToBottom, 120);
      });
    };

    $scope.keyDown = function (e) {
      if (e.keyCode === 13 && !e.shiftKey) {
        e.preventDefault();
        $scope.send();
      }
    };

    $scope.clearChat = function () {
      $scope.messages = [];
    };

    $scope.useSuggestion = function (text) {
      $scope.question = text;
      $timeout(function () {
        document.getElementById('question-input').focus();
      });
    };

    $scope.formatTime = function (date) {
      if (!date) return '';
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    };

    function _scrollToBottom() {
      var el = document.getElementById('chat-messages');
      if (el) el.scrollTop = el.scrollHeight;
    }
  }]);
